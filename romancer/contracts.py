"""Declarative adapter inventory and read-only, revision-bound profile contracts."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from . import ROMANCER_VERSION

MAX_RULES = 1024
MAX_RULE_BYTES = 1024 * 1024
MAX_TOTAL_RULE_BYTES = 8 * 1024 * 1024
MAX_LEGACY_JSON_BYTES = 8 * 1024 * 1024
MAX_PROVENANCE_BYTES = 8 * 1024 * 1024
MAX_CONTRACT_JSON_BYTES = 32 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100000
HASH_CHUNK_BYTES = 1024 * 1024
ADAPTER_IDS = frozenset({"nes", "snes", "genesis", "gb", "gbc", "gba"})


def _result(scope: str) -> dict:
    return {"tool": "ROMancer", "tool_version": ROMANCER_VERSION, "schema_version": 2,
            "scope": scope, "write_authorized": False}


def adapter_inventory() -> dict:
    definitions = (
        ("nes", "experimental", "iNES identification; NES 2.0 extended fields are not fully decoded."),
        ("snes", "experimental", "Header scoring and address mapping are heuristic, not mapper-state proof."),
        ("genesis", "supported", "SEGA cartridge header identification only; mapper and bank-switch behavior is not established."),
        ("gb", "supported", "Validated DMG cartridge header and declared banks."),
        ("gbc", "supported", "Validated CGB-compatible/Color-only header and declared banks; gameplay needs native evidence."),
        ("gba", "supported", "Header/fixed-byte identification and checksum reporting; this is not runtime compatibility proof."),
    )
    adapters = []
    for identifier, status, reason in definitions:
        implementation = "romancer/system_formats/gb.py" if identifier in ("gb","gbc") else f"romancer/systems/{identifier}.py"
        capabilities = {
            "identification": {"status": status, "reason": reason, "implementation": implementation},
            "raw_inspection": {"status": "supported", "reason": "Read-only bytes and header inspection; unknown layouts remain inspectable.", "implementation": "romancer/rom_ident.py"},
            "structured_resource_write": {"status": "unsupported", "reason": "No revision-bound structured resource writer is registered; generic byte tools do not prove ownership.", "implementation": "romancer/contracts.py"},
            "expert_payload_write": {"status": "unsupported", "reason": "No expert payload transaction is registered for this adapter.", "implementation": "romancer/contracts.py"},
            "runtime_control": {"status": "unavailable", "reason": "A measured worker handshake is required; executable discovery is insufficient.", "implementation": "romancer/v22_30.py:bridge_probe"},
        }
        adapters.append({"id": identifier, "capabilities": capabilities})
    return {**_result("adapter_inventory"), "ok": True, "adapters": adapters,
            "policy": "Declarative inventory only. Legacy APIs remain outside this contract; identification does not authorize writes or establish runtime compatibility."}


def _canonical_json(value, limit: int) -> bytes:
    nodes, approximate_bytes = 0, 0
    active = set()

    def visit(item, depth):
        nonlocal nodes, approximate_bytes
        nodes += 1
        if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
            raise ValueError("JSON depth or node budget exceeded")
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active:
                raise ValueError("cyclic objects are not JSON")
            active.add(id(item))
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError("JSON object keys must be strings")
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(id(item))
        elif kind is str:
            if len(item) > limit:
                raise ValueError("JSON byte budget exceeded")
            approximate_bytes += len(item.encode("utf-8"))
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError("JSON numbers must be finite")
        elif kind not in (int, bool, type(None)):
            raise ValueError("value is not a JSON type")
        if approximate_bytes > limit:
            raise ValueError("JSON byte budget exceeded")

    visit(value, 0)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(encoded) > limit:
        raise ValueError("canonical JSON byte budget exceeded")
    return encoded


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError(f"nonfinite JSON number: {value}")


def _identity(info):
    # Windows path stat and handle fstat can expose different ctime semantics.
    # Re-hashing the held file supplies the byte check independently of timestamps.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


class _SourceChanged(ValueError):
    pass


def _assert_stable(path, stream, initial):
    try:
        if _identity(os.fstat(stream.fileno())) != _identity(initial) or _identity(path.stat()) != _identity(initial):
            raise _SourceChanged("artifact identity or metadata changed during checking")
    except OSError as exc:
        raise _SourceChanged("artifact path changed or became unavailable") from exc


def _read_json_file(path: Path, limit: int) -> tuple[dict, bytes]:
    path = Path(path).absolute()
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("JSON input must be a regular file")
    if before.st_size > limit:
        raise ValueError("JSON input exceeds byte budget")
    with path.open("rb", buffering=0) as stream:
        initial = os.fstat(stream.fileno())
        if _identity(initial) != _identity(before):
            raise _SourceChanged("JSON input changed while opening")
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("JSON input exceeds byte budget")
        if len(raw) != initial.st_size:
            raise _SourceChanged("JSON input size changed while reading")
        _assert_stable(path, stream, initial)
        # A second bounded read also detects same-size edits with restored mtime.
        stream.seek(0)
        if stream.read(limit + 1) != raw:
            raise _SourceChanged("JSON bytes changed while reading")
        _assert_stable(path, stream, initial)
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_nonfinite)
        if type(obj) is not dict:
            raise ValueError("JSON input must be an object")
        _canonical_json(obj, limit)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds supported depth") from exc
    return obj, raw


def load_contract(path: Path) -> dict:
    """Bounded, duplicate-key rejecting loader for CLI contract consumers."""
    profile, _ = _read_json_file(path, MAX_CONTRACT_JSON_BYTES)
    return validate_contract(profile)["normalized_profile"]


def _label(value, field: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"{field} must be a nonblank label of at most 256 characters without controls")
    return value


def validate_contract(profile: dict) -> dict:
    if type(profile) is not dict:
        raise ValueError("profile must be a JSON object")
    required = {"schema_version", "id", "version", "system", "accepted_sha256", "rules"}
    if not required <= profile.keys() or profile.keys() - required - {"provenance"}:
        raise ValueError("profile fields must exactly match the version 2 contract")
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 2:
        raise ValueError("schema_version must be integer 2")
    _label(profile["id"], "id")
    _label(profile["version"], "version")
    if type(profile["system"]) is not str or profile["system"] not in ADAPTER_IDS:
        raise ValueError("system must name a registered adapter")
    revisions = profile["accepted_sha256"]
    if type(revisions) is not list or not revisions:
        raise ValueError("accepted_sha256 must be a nonempty list")
    normalized_revisions = []
    for digest in revisions:
        if type(digest) is not str or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise ValueError("accepted revisions must be full SHA-256 hexadecimal strings")
        normalized_revisions.append(digest.lower())
    if len(set(normalized_revisions)) != len(normalized_revisions):
        raise ValueError("duplicate accepted revision")
    rules = profile["rules"]
    if type(rules) is not list or len(rules) > MAX_RULES:
        raise ValueError("rules must be a list with at most 1024 entries")
    normalized_rules, total = [], 0
    for rule in rules:
        if type(rule) is not dict or set(rule) != {"resource", "offset", "length", "expected_hex"}:
            raise ValueError("rule fields must exactly match the contract")
        _label(rule["resource"], "resource")
        offset, length, expected = rule["offset"], rule["length"], rule["expected_hex"]
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a nonnegative integer, not boolean")
        if type(length) is not int or not 0 < length <= MAX_RULE_BYTES:
            raise ValueError("length must be a positive integer no larger than 1 MiB")
        total += length
        if total > MAX_TOTAL_RULE_BYTES:
            raise ValueError("total rule length exceeds 8 MiB")
        if type(expected) is not str or len(expected) != length * 2 or re.fullmatch(r"[0-9a-fA-F]+", expected) is None:
            raise ValueError("expected_hex must encode exactly length bytes without whitespace")
        normalized_rules.append({**rule, "expected_hex": expected.lower()})
    normalized_rules.sort(key=lambda rule: rule["offset"])
    end = 0
    for rule in normalized_rules:
        if rule["offset"] < end:
            raise ValueError("rules overlap in the single artifact address space")
        end = rule["offset"] + rule["length"]
    if "provenance" in profile:
        _canonical_json(profile["provenance"], MAX_PROVENANCE_BYTES)
    normalized = {**profile, "accepted_sha256": sorted(normalized_revisions), "rules": normalized_rules}
    encoded = _canonical_json(normalized, MAX_CONTRACT_JSON_BYTES)
    return {**_result("profile_schema"), "ok": True, "status": "CONTRACT_VALID",
            "profile_id": profile["id"], "profile_version": profile["version"], "system": profile["system"],
            "profile_sha256": hashlib.sha256(encoded).hexdigest(), "normalized_profile": json.loads(encoded),
            "rule_count": len(rules), "rule_bytes": total,
            "coverage": "declared_rules" if rules else "identity_only"}


def _hash_stream(stream) -> str:
    stream.seek(0)
    remaining = os.fstat(stream.fileno()).st_size
    digest = hashlib.sha256()
    while remaining:
        chunk = stream.read(min(HASH_CHUNK_BYTES, remaining))
        if not chunk:
            raise _SourceChanged("artifact was truncated during hashing")
        remaining -= len(chunk)
        digest.update(chunk)
    if stream.read(1):
        raise _SourceChanged("artifact grew during hashing")
    return digest.hexdigest()


def _read_rule(stream, rule):
    stream.seek(rule["offset"])
    return stream.read(rule["length"])


def check_contract(profile: dict, artifact: Path) -> dict:
    validation = validate_contract(profile)
    normalized = validation["normalized_profile"]
    path = Path(artifact).absolute()
    result = {**_result("profile_preconditions"),
              **{key: validation[key] for key in ("profile_id", "profile_version", "profile_sha256", "system", "rule_count", "coverage")},
              "artifact_path": str(path), "artifact_sha256": None, "revision_match": False,
              "ok": False, "status": "BLOCKED", "rules": [],
              "policy": "Read-only profile identity and byte preconditions only. No format identification, resource ownership, runtime proof, or write authorization is established; a supported writer must revalidate its own preconditions."}
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            result.update(error_code="ARTIFACT_UNAVAILABLE", error="artifact must be a regular file")
            return result
        with path.open("rb", buffering=0) as stream:
            initial = os.fstat(stream.fileno())
            if _identity(initial) != _identity(before):
                raise _SourceChanged("artifact changed while opening")
            observed = _hash_stream(stream)
            result["artifact_sha256"] = observed
            _assert_stable(path, stream, initial)
            result["revision_match"] = observed in normalized["accepted_sha256"]
            if not result["revision_match"]:
                result.update(status="PRECONDITIONS_FAILED", error_code="REVISION_MISMATCH", error="artifact SHA-256 is not an accepted revision")
                return result
            mismatch = None
            for rule in normalized["rules"]:
                row = {**rule, "ok": False}
                if rule["offset"] > initial.st_size - rule["length"]:
                    row["error_code"] = "RULE_OUT_OF_BOUNDS"
                else:
                    actual = _read_rule(stream, rule)
                    row.update(observed_hex=actual.hex(), ok=actual == bytes.fromhex(rule["expected_hex"]))
                    if not row["ok"]:
                        row["error_code"] = "RULE_MISMATCH"
                result["rules"].append(row)
                if not row["ok"] and mismatch is None:
                    mismatch = row["error_code"]
            _assert_stable(path, stream, initial)
            if _hash_stream(stream) != observed:
                raise _SourceChanged("artifact bytes changed during checking")
            _assert_stable(path, stream, initial)
            if mismatch:
                result.update(status="PRECONDITIONS_FAILED", error_code=mismatch, error="one or more declared rule preconditions did not match")
            else:
                result.update(ok=True, status="PRECONDITIONS_PASSED")
    except _SourceChanged as exc:
        result.update(ok=False, status="BLOCKED", error_code="ARTIFACT_CHANGED", error=str(exc))
    except OSError as exc:
        result.update(ok=False, status="BLOCKED", error_code="ARTIFACT_UNAVAILABLE", error=str(exc))
    return result


def import_legacy_profile(path: Path) -> dict:
    source = Path(path).absolute()
    original, raw = _read_json_file(source, MAX_LEGACY_JSON_BYTES)
    return {**_result("legacy_profile_import"), "ok": True, "status": "HISTORICAL_UNVERIFIED",
            "source_path": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
            "original_json": original, "provenance": "imported_historical_json",
            "policy": "Original JSON is preserved as historical assertions only. No accepted revisions, current facts, verified offsets, final text, or write authority are inferred."}
