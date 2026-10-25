from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib
import json
import math
import re
from .util import write_json
from .patch_ledger_v10 import ledger_check
from .coverage_v10 import coverage_report


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def _read(path: str | Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"),
                     object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object")
    return obj


def _assertion_status(obj: dict[str, Any]) -> str:
    if not isinstance(obj, dict):
        raise ValueError("assertion must be an object")
    flags, statuses = [], []
    for key in ("ok", "pass"):
        if key in obj:
            if type(obj[key]) is not bool:
                raise ValueError(f"{key} must be a boolean")
            flags.append(obj[key])
    for key in ("status", "gate_status"):
        if key in obj:
            value = obj[key]
            if not isinstance(value, str) or value.upper() not in {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "GATES_PASSED"}:
                raise ValueError(f"unsupported {key}")
            statuses.append("PASS" if value.upper() == "GATES_PASSED" else value.upper())
    if len(set(flags)) > 1 or len(set(statuses)) > 1:
        raise ValueError("conflicting assertion statuses")
    if statuses:
        status = statuses[0]
        if flags and flags[0] != (status == "PASS"):
            raise ValueError("conflicting assertion flag and status")
        return status
    if not flags:
        raise ValueError("missing assertion status")
    return "PASS" if flags[0] else "FAIL"


def _result_ok(obj: dict[str, Any]) -> bool:
    return _assertion_status(obj) == "PASS"


def _validate_gates(gates: Any, kinds: set[str], default_kind: str) -> list[dict[str, Any]]:
    if not isinstance(gates, list) or not gates:
        raise ValueError("gates must be a nonempty list")
    names, validated = set(), []
    for gate in gates:
        if not isinstance(gate, dict):
            raise ValueError("each gate must be an object")
        name = gate.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each gate requires a nonempty name")
        name = name.strip()
        if name.casefold() in names:
            raise ValueError(f"duplicate gate name: {name}")
        names.add(name.casefold())
        required = gate.get("required", True)
        if type(required) is not bool:
            raise ValueError(f"required must be a boolean: {name}")
        kind = gate.get("kind", default_kind)
        if not isinstance(kind, str) or kind not in kinds:
            raise ValueError(f"unsupported gate kind: {kind}")
        fields = {"name", "kind", "required"}
        if default_kind == "assertion":
            fields.update({"status", "gate_status", "ok", "pass"})
        else:
            fields.add("path")
            fields.update({"minimum"} if kind == "coverage" else {"algorithm", "expected"} if kind == "hash" else set())
        if set(gate) - fields:
            raise ValueError(f"unsupported fields for {kind} gate: {sorted(set(gate) - fields)}")
        validated.append({**gate, "name": name, "kind": kind, "required": required})
    if not any(g["required"] for g in validated):
        raise ValueError("at least one required gate must declare the evaluation scope")
    return validated


def _gate_summary(rows: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    critical = [g for g in rows if g["required"] and not g["ok"]]
    incomplete = any(g["gate_status"] in {"BLOCKED", "NOT_RUN"} for g in rows)
    ok = bool(rows) and any(g["required"] for g in rows) and not (critical or errors or incomplete)
    if ok:
        status = "GATES_PASSED"
    elif errors or any(g["gate_status"] == "BLOCKED" for g in rows):
        status = "BLOCKED"
    elif any(g["gate_status"] == "FAIL" for g in critical):
        status = "FAIL"
    else:
        status = "NOT_RUN"
    return {"schema_version": 2, "ok": ok, "status": status,
            "release_status": "GATES_PASSED" if ok else "BLOCKED",
            "scope": {"required_gates": [g["name"] for g in rows if g["required"]]},
            "provenance": "declared_gate_evaluation", "gate_count": len(rows),
            "critical_failures": critical, "gates": rows, "validation_errors": errors,
            "policy": "Only the declared required scope is evaluated. Imported assertions are not measured runtime proof; no full-game certification, freshness, or evidence lineage is established."}


def _validate_coverage(obj: dict[str, Any]) -> None:
    categories = obj.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("coverage requires nonempty categories")
    for rec in categories.values():
        if not isinstance(rec, dict):
            raise ValueError("coverage category must be an object")
        for key in ("known", "hit", "excluded"):
            values = rec.get(key, [])
            if not isinstance(values, list) or any(not (type(x) is int or isinstance(x, str) and x) for x in values):
                raise ValueError(f"coverage {key} must contain string or integer identifiers")


def _validate_ledger(obj: dict[str, Any]) -> None:
    allocations = obj.get("allocations")
    if not isinstance(allocations, list):
        raise ValueError("ledger requires an allocations list")
    for allocation in allocations:
        if not isinstance(allocation, dict):
            raise ValueError("allocation must be an object")
        values = []
        for key in ("start", "end"):
            value = allocation.get(key)
            if type(value) is int:
                values.append(value)
            elif isinstance(value, str) and re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", value):
                values.append(int(value, 16 if value.lower().startswith("0x") else 10))
            else:
                raise ValueError("allocation bounds must be integers")
        if values[0] < 0 or values[1] < values[0]:
            raise ValueError("invalid allocation range")


def certify(manifest: str, out: str | None = None) -> dict[str, Any]:
    manifest_path = Path(manifest).resolve()
    rows, errors = [], []
    try:
        obj = _read(manifest_path)
        gates = _validate_gates(obj.get("gates"), {"json", "ledger", "coverage", "hash"}, "json")
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        gates = []
        errors.append(str(exc))
    for gate in gates:
        kind = gate["kind"]
        detail = {"name": gate["name"], "kind": kind, "required": gate["required"],
                  "ok": False, "gate_status": "BLOCKED", "measured": False,
                  "provenance": "not_evaluated"}
        try:
            raw_path = gate.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError("gate requires a nonempty artifact path")
            path = (manifest_path.parent / raw_path).resolve()
            detail["path"] = str(path)
            if not path.is_file():
                raise ValueError("gate artifact is missing or is not a regular file")
            if kind == "json":
                detail.update(provenance="imported_assertion", evidence_scope="supplied JSON status")
                assertion = _read(path)
                status = _assertion_status(assertion)
                detail.update(asserted_status=assertion.get("status", assertion.get("gate_status", status)))
                if "scope" in assertion:
                    detail["asserted_scope"] = assertion["scope"]
            elif kind == "ledger":
                _validate_ledger(_read(path))
                result = ledger_check(str(path))
                status = "PASS" if _result_ok(result) else "FAIL"
                detail.update(provenance="executed_validator", measured=True,
                              evidence_scope="overlaps in supplied allocation ranges only",
                              overlaps=len(result["overlaps"]))
            elif kind == "coverage":
                minimum = gate.get("minimum", 100)
                if type(minimum) not in (int, float) or not math.isfinite(minimum) or not 0 <= minimum <= 100:
                    raise ValueError("minimum must be a finite number from 0 through 100")
                _validate_coverage(_read(path))
                result = coverage_report(str(path))
                if result["overall"]["eligible"] <= 0:
                    raise ValueError("coverage scope has no eligible identifiers")
                eligible, hit = result["overall"]["eligible"], result["overall"]["hit"]
                pct = 100.0 * hit / eligible
                # Compare counts, not the legacy report's rounded percentage.
                numerator, denominator = minimum.as_integer_ratio()
                status = "PASS" if 100 * hit * denominator >= numerator * eligible else "FAIL"
                detail.update(provenance="executed_validator", measured=True,
                              input_provenance="imported_assertion", coverage_percent=pct,
                              minimum=minimum, evidence_scope="coverage arithmetic on supplied hit assertions only")
            else:
                algorithm = gate.get("algorithm", "sha256")
                if algorithm not in ("sha256", "sha384", "sha512", "sha1", "md5"):
                    raise ValueError("unsupported fixed-length hash algorithm")
                digest = hashlib.new(algorithm)
                expected = gate.get("expected")
                if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{%d}" % (digest.digest_size * 2), expected):
                    raise ValueError("expected must be a complete hexadecimal digest")
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                observed = digest.hexdigest()
                status = "PASS" if observed == expected.lower() else "FAIL"
                detail.update(provenance="measured_hash", measured=True, algorithm=algorithm,
                              observed=observed, expected=expected, evidence_scope="artifact digest equality only")
            detail.update(ok=status == "PASS", gate_status=status)
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            detail["error"] = str(exc)
        rows.append(detail)
    result = {"tool": "ROMancer", "feature": "v10 gate evaluation", "manifest": str(manifest_path),
              **_gate_summary(rows, errors)}
    if out:
        write_json(out, result)
    return result
