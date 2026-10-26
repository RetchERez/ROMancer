from __future__ import annotations

"""ROMancer v22 through v30 cumulative lab expansion.

This module adds project-vault control, bridge templates, visual/text oracles,
SDK generation, patch-synthesis helpers, route validation, QA matrices, studio
reports, and v30 certification orchestration. It is deliberately conservative:
executable discovery does not establish live emulator control.
"""


import hashlib
import json
import ntpath
import os

import shutil
import stat
import struct
import tempfile
import unicodedata
import zipfile
import zlib
from contextlib import ExitStack

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ips import create_ips
from .diffing import byte_diff
from .util import write_json
from .certify_v10 import _read, _assertion_status, _validate_gates, _gate_summary

VERSION = "30.0.0"

FORBIDDEN_RELEASE_SUFFIXES = {
    ".sfc", ".smc", ".nes", ".fds", ".gba", ".gb", ".gbc", ".gg", ".sms",
    ".gen", ".bin", ".iso", ".cue", ".chd", ".ccd", ".img", ".sub",
    ".n64", ".z64", ".v64", ".srm", ".sav", ".state", ".st0", ".st1",
    ".bios", ".rom",
}
SAFE_RELEASE_SUFFIXES = {
    ".txt", ".md", ".json", ".jsonl", ".tsv", ".csv", ".ips", ".bps", ".py",
    ".sh", ".html", ".css", ".svg", ".sha256", ".tbl", ".asm", ".yml", ".yaml",
    ".ps1", ".c", ".log",  # Tool launchers, mock core source, and synthetic trace fixtures.
    ".cht",  # Synthetic text cheat fixtures; contents still require manual review.
}
STATUS_PASS = {"pass", "passed", "verified", "fixed", "certified", "ok"}
STATUS_FAIL = {"fail", "failed", "blocked", "error", "broken"}

PACKAGE_MAX_ENTRIES = 10000
PACKAGE_MAX_MEMBER_BYTES = 64 * 1024 * 1024
PACKAGE_MAX_TOTAL_BYTES = 256 * 1024 * 1024
PACKAGE_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
PACKAGE_MAX_DIRECTORY_BYTES = 8 * 1024 * 1024
PACKAGE_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".whl"}
PACKAGE_PRIVATE_PARTS = {
    "private", "reports", "evidence", "sources", "bios", "roms", "saves", "states",
    "work_private", ".git", "__pycache__", ".superpowers", ".venv", "dist",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_id(parts: Iterable[str]) -> str:
    raw = "\x1f".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:24]


def read_jsonish(obj: str | Path | dict[str, Any] | list[Any] | None, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, (dict, list)):
        return obj
    s = str(obj)
    p = Path(s)
    if p.exists():
        text = p.read_text("utf-8", errors="replace")
    else:
        text = s
    try:
        return json.loads(text)
    except Exception:
        return default if default is not None else {"raw": text}


def write_if(out: str | None, data: Any) -> Any:
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            p.write_text(data, encoding="utf-8", newline="\n")
        else:
            write_json(str(p), data)
    return data


def load_manifest(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    for name in ["romancer_project.json", "manifest.json", "CURRENT_FACTS.json"]:
        p = root / name
        if p.exists():
            data = read_jsonish(p, {})
            if isinstance(data, dict):
                data.setdefault("root", str(root))
                return data
    return {"root": str(root), "project_name": root.name, "created_utc": None, "schema": "romancer-project-v30"}


def save_manifest(project: str | Path, manifest: dict[str, Any]) -> None:
    root = Path(project)
    root.mkdir(parents=True, exist_ok=True)
    write_json(str(root / "romancer_project.json"), manifest)


def vault_dirs(root: Path) -> list[Path]:
    return [
        root / "sources",
        root / "patches",
        root / "reports",
        root / "evidence",
        root / "qa",
        root / "routes",
        root / "sdk",
        root / "release",
        root / "handoff",
        root / "artifacts",
    ]


def vault_init(project: str, name: str = "", system: str = "", goal: str = "", out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    root.mkdir(parents=True, exist_ok=True)
    for d in vault_dirs(root):
        d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "romancer-project-v30",
        "tool": "ROMancer",
        "version": VERSION,
        "project_name": name or root.name,
        "system": system or "unknown",
        "goal": goal,
        "created_utc": now_iso(),
        "root": str(root),
        "status_labels": ["verified", "fixed", "not reachable", "not inspected", "release candidate", "final"],
        "release_policy": "Do not include ROMs, BIOS, emulator cores, save states, commercial screenshots, or commercial game assets",
    }
    save_manifest(root, manifest)
    ledger = root / "artifacts" / "artifact_ledger.json"
    if not ledger.exists():
        write_json(str(ledger), {"schema": "romancer-artifact-ledger-v30", "artifacts": []})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v22 project vault init", "ok": True, "project": str(root), "manifest": str(root / "romancer_project.json"), "directories": [str(d) for d in vault_dirs(root)]}
    return write_if(out, result)


def vault_status(project: str, out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    manifest = load_manifest(root)
    required = vault_dirs(root)
    missing = [str(d) for d in required if not d.exists()]
    counts: dict[str, int] = {}
    for d in required:
        counts[d.name] = len([p for p in d.rglob("*") if p.is_file()]) if d.exists() else 0
    ledger_path = root / "artifacts" / "artifact_ledger.json"
    ledger = read_jsonish(ledger_path, {"artifacts": []}) if ledger_path.exists() else {"artifacts": []}
    result = {
        "tool": "ROMancer",
        "version": VERSION,
        "feature": "v22 project vault status",
        "ok": root.exists() and not missing,
        "project": str(root),
        "project_name": manifest.get("project_name", root.name),
        "system": manifest.get("system", "unknown"),
        "goal": manifest.get("goal", ""),
        "missing_directories": missing,
        "file_counts": counts,
        "artifact_count": len(ledger.get("artifacts", [])),
    }
    return write_if(out, result)


def artifact_add(project: str, path: str, kind: str = "artifact", reason: str = "", status: str = "not inspected", parent: str = "", out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    p = Path(path)
    if not p.exists():
        result = {"tool": "ROMancer", "version": VERSION, "feature": "v22 artifact add", "ok": False, "error": "artifact path does not exist", "path": str(p)}
        return write_if(out, result)
    ledger_path = root / "artifacts" / "artifact_ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = read_jsonish(ledger_path, {"schema": "romancer-artifact-ledger-v30", "artifacts": []})
    entry = {
        "artifact_id": stable_id([str(p.resolve()), sha256_file(p), kind, reason]),
        "path": str(p),
        "name": p.name,
        "kind": kind,
        "reason": reason,
        "status": status,
        "parent": parent,
        "size_bytes": p.stat().st_size,
        "sha256": sha256_file(p),
        "added_utc": now_iso(),
    }
    ledger.setdefault("artifacts", []).append(entry)
    write_json(str(ledger_path), ledger)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v22 artifact add", "ok": True, "entry": entry, "ledger": str(ledger_path)}
    return write_if(out, result)


def artifact_audit(project: str, out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    ledger_path = root / "artifacts" / "artifact_ledger.json"
    ledger = read_jsonish(ledger_path, {"artifacts": []}) if ledger_path.exists() else {"artifacts": []}
    rows = []
    ok = True
    for e in ledger.get("artifacts", []):
        p = Path(e.get("path", ""))
        exists = p.exists()
        sha_ok = False
        forbidden = p.suffix.lower() in FORBIDDEN_RELEASE_SUFFIXES
        if exists and p.is_file():
            try:
                sha_ok = sha256_file(p) == e.get("sha256")
            except Exception:
                sha_ok = False
        row = {"artifact_id": e.get("artifact_id"), "path": str(p), "exists": exists, "sha256_ok": sha_ok, "forbidden_suffix": forbidden, "status": e.get("status", "unknown")}
        if not exists or not sha_ok or forbidden:
            ok = False
        rows.append(row)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v22 artifact audit", "ok": ok, "artifact_count": len(rows), "artifacts": rows}
    return write_if(out, result)


def artifact_lineage(project: str, out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    ledger_path = root / "artifacts" / "artifact_ledger.json"
    ledger = read_jsonish(ledger_path, {"artifacts": []}) if ledger_path.exists() else {"artifacts": []}
    nodes = []
    edges = []
    for e in ledger.get("artifacts", []):
        aid = e.get("artifact_id")
        nodes.append({"id": aid, "name": e.get("name"), "kind": e.get("kind"), "status": e.get("status")})
        if e.get("parent"):
            edges.append({"from": e.get("parent"), "to": aid})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v22 artifact lineage", "ok": True, "nodes": nodes, "edges": edges}
    return write_if(out, result)


def _package_zip_preflight(stream) -> tuple[int, int]:
    """Bound central-directory allocation before ZipFile loads member metadata."""
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    if size > PACKAGE_MAX_ARCHIVE_BYTES:
        raise ValueError("archive file size budget exceeded")
    stream.seek(max(0, size - 65557))
    tail = stream.read(65557)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise ValueError("missing or truncated ZIP end record")
    _, disk, start_disk, local_entries, entries, directory_size, directory_offset, comment = struct.unpack_from("<4s4H2LH", tail, offset)
    if len(tail) - offset != 22 + comment:
        raise ValueError("trailing payload or malformed ZIP comment")
    if disk or start_disk or local_entries != entries or entries == 65535:
        raise ValueError("multidisk and ZIP64 archives are unsupported")
    if entries > PACKAGE_MAX_ENTRIES or directory_size > PACKAGE_MAX_DIRECTORY_BYTES:
        raise ValueError("ZIP metadata budget exceeded")
    end_offset = size - len(tail) + offset
    if directory_offset + directory_size != end_offset:
        raise ValueError("inconsistent ZIP directory extent or unsupported ZIP64 metadata")
    stream.seek(0)
    return entries, directory_offset


def _package_zip_chunks(stream, info, boundary):
    """Validate bounded raw member output independently of ZipExtFile's size cap."""
    stream.seek(info.header_offset)
    header = stream.read(30)
    if len(header) != 30:
        raise ValueError("truncated ZIP local header")
    signature, version, flags, method, _, _, crc, compressed, size, name_len, extra_len = struct.unpack("<4s5H3I2H", header)
    if (signature != b"PK\x03\x04" or flags != info.flag_bits or method != info.compress_type
            or flags & ~0x080E or version > 20):
        raise ValueError("unsupported or inconsistent ZIP local header")
    encoded_name = stream.read(name_len)
    name = encoded_name.decode("utf-8" if flags & 0x800 else "cp437")
    if len(encoded_name) != name_len or name != info.orig_filename:
        raise ValueError("ZIP local/central member names differ")
    data_start = info.header_offset + 30 + name_len + extra_len
    data_end = data_start + info.compress_size
    if data_end > boundary or data_start > boundary:
        raise ValueError("ZIP member overlaps another record")
    if flags & 8:
        if crc not in (0, info.CRC) or compressed not in (0, info.compress_size) or size not in (0, info.file_size):
            raise ValueError("inconsistent ZIP descriptor placeholders")
    elif (crc, compressed, size) != (info.CRC, info.compress_size, info.file_size):
        raise ValueError("ZIP local/central sizes or CRC differ")
    stream.seek(data_start)
    remaining, count, observed_crc = info.compress_size, 0, 0
    decoder = zlib.decompressobj(-15) if method == zipfile.ZIP_DEFLATED else None
    limit = min(info.file_size, PACKAGE_MAX_MEMBER_BYTES, PACKAGE_MAX_TOTAL_BYTES)
    while remaining:
        encoded = stream.read(min(65536, remaining))
        if not encoded:
            raise ValueError("truncated ZIP compressed payload")
        remaining -= len(encoded)
        pending = encoded
        while pending:
            if decoder is None:
                output, pending = pending, b""
            else:
                if decoder.eof:
                    raise ValueError("bytes after DEFLATE end of stream")
                output = decoder.decompress(pending, min(65536, limit - count + 1))
                pending = decoder.unconsumed_tail
                if decoder.unused_data:
                    raise ValueError("unused bytes in DEFLATE payload")
            count += len(output)
            if count > limit:
                raise ValueError("actual ZIP output exceeds declared size or byte budget")
            observed_crc = zlib.crc32(output, observed_crc)
            if output:
                yield output
    if decoder is not None:
        # Drain buffered output with the same bound; never call unbounded flush().
        while not decoder.eof:
            output = decoder.decompress(b"", min(65536, limit - count + 1))
            count += len(output)
            if count > limit:
                raise ValueError("actual ZIP output exceeds declared size or byte budget")
            observed_crc = zlib.crc32(output, observed_crc)
            if output:
                yield output
            else:
                break
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("incomplete or trailing DEFLATE stream")
    if count != info.file_size or observed_crc != info.CRC:
        raise ValueError("actual ZIP size or CRC mismatch")
    trailer_size = boundary - data_end
    if flags & 8:
        if trailer_size not in (12, 16):
            raise ValueError("unsupported or malformed ZIP data descriptor")
        stream.seek(data_end)
        descriptor = stream.read(trailer_size)
        if len(descriptor) != trailer_size:
            raise ValueError("truncated ZIP data descriptor")
        if trailer_size == 16:
            if descriptor[:4] != b"PK\x07\x08":
                raise ValueError("invalid ZIP data descriptor signature")
            descriptor = descriptor[4:]
        if struct.unpack("<3I", descriptor) != (info.CRC, info.compress_size, count):
            raise ValueError("ZIP data descriptor differs from actual member")
    elif trailer_size:
        raise ValueError("unclassified bytes between ZIP records")


def _package_has_zip_end(tail: bytes, size: int) -> bool:
    """Inspect the bounded ZIP end-record window without opening a nested archive."""
    offset = tail.rfind(b"PK\x05\x06")
    while offset >= 0:
        if len(tail) - offset >= 22:
            _, _, _, _, entries, directory_size, directory_offset, comment = struct.unpack_from("<4s4H2LH", tail, offset)
            end_position = size - len(tail) + offset
            if (offset + 22 + comment <= len(tail)
                    and directory_offset + directory_size <= end_position
                    and (directory_size >= 46 or entries == directory_size == 0)):
                return True
        offset = tail.rfind(b"PK\x05\x06", 0, offset)
    return False


def release_boundary_scan(root: str, out: str | None = None) -> dict[str, Any]:
    p = Path(root)
    files, findings, seen = [], [], {}
    entry_count = total_bytes = 0

    def register(name, size, directory=False):
        nonlocal entry_count, total_bytes
        entry_count += 1
        if entry_count > PACKAGE_MAX_ENTRIES:
            raise ValueError("package entry count budget exceeded")
        clean = name[:-1] if directory and name.endswith("/") else name
        parts = clean.split("/")
        if (not clean or "\\" in name or any(ord(c) < 32 for c in name)
                or any(c in name for c in ':<>"|?*')
                or any(part in ("", ".", "..") or part.endswith((".", " ")) for part in parts)
                or any(ntpath.isreserved(part) for part in parts)):
            raise ValueError(f"unsafe package path: {name!r}")
        key = unicodedata.normalize("NFC", clean).casefold()
        if key in seen:
            raise ValueError(f"duplicate package path: {name}")
        if any(seen.get("/".join(key.split("/")[:i])) is False for i in range(1, len(parts))):
            raise ValueError(f"file used as parent directory: {name}")
        if not directory and any(old.startswith(key + "/") for old in seen):
            raise ValueError(f"file conflicts with directory: {name}")
        seen[key] = directory
        excluded_path = any(part.casefold() in PACKAGE_PRIVATE_PARTS for part in parts)
        if directory:
            if size:
                raise ValueError("directory archive entry contains data")
            if excluded_path:
                findings.append({"path": name, "size_bytes": 0, "forbidden": True,
                                 "reason": "excluded_directory"})
            return False
        if size < 0 or size > PACKAGE_MAX_MEMBER_BYTES:
            raise ValueError("package member size budget exceeded")
        total_bytes += size
        if total_bytes > PACKAGE_MAX_TOTAL_BYTES:
            raise ValueError("package uncompressed size budget exceeded")
        suffix = Path(clean).suffix.lower()
        forbidden = suffix in FORBIDDEN_RELEASE_SUFFIXES or excluded_path
        nested = suffix in PACKAGE_ARCHIVE_SUFFIXES
        known = suffix in SAFE_RELEASE_SUFFIXES
        item = {"path": name, "size_bytes": size, "suffix": suffix,
                "forbidden": forbidden, "safe_known": known}
        files.append(item)
        if forbidden or nested or not known:
            findings.append({**item, "reason": "forbidden_member" if forbidden else "nested_archive" if nested else "unknown_member"})
            return False
        return True

    def check_chunks(chunks, size, name):
        count, prefix, tail = 0, b"", b""
        for chunk in chunks:
            count += len(chunk)
            if count > size or count > PACKAGE_MAX_MEMBER_BYTES:
                raise ValueError("member exceeded declared size or read budget")
            if len(prefix) < 512:
                prefix += chunk[:512 - len(prefix)]
            tail = (tail + chunk)[-65557:]
        if count != size:
            raise ValueError("member size mismatch")
        if (prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b", b"BZh",
                               b"\xfd7zXZ\x00", b"7z\xbc\xaf\x27\x1c", b"Rar!"))
                or prefix[257:262] == b"ustar" or _package_has_zip_end(tail, count)):
            raise ValueError(f"nested archive signature: {name}")

    def check_file(path, name):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"links are not permitted: {name}")
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"non-regular member: {name}")
        size = path.stat().st_size
        if register(name, size):
            with path.open("rb") as stream:
                check_chunks(iter(lambda: stream.read(65536), b""), size, name)

    try:
        if p.is_symlink() or p.is_junction():
            raise ValueError("package root must not be a link")
        if p.is_file() and (p.suffix.lower() == ".zip" or zipfile.is_zipfile(p)):
            if p.suffix.lower() != ".zip":
                raise ValueError("ZIP package requires an explicit .zip suffix")
            with ExitStack() as resources:
                stream = resources.enter_context(p.open("rb"))
                expected_entries, directory_offset = _package_zip_preflight(stream)
                archive = resources.enter_context(zipfile.ZipFile(stream, "r"))
                infos = archive.infolist()
                if len(infos) != expected_entries or len(infos) > PACKAGE_MAX_ENTRIES:
                    raise ValueError("ZIP entry count mismatch or budget exceeded")
                approved = []
                for info in infos:
                    name = info.orig_filename
                    mode = stat.S_IFMT(info.external_attr >> 16)
                    if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise ValueError(f"non-regular archive member: {name}")
                    if (info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                            or (mode == stat.S_IFDIR and not info.is_dir())):
                        raise ValueError(f"unsupported archive member encoding: {name}")
                    permitted = register(name, info.file_size, info.is_dir())
                    if permitted or info.is_dir():
                        approved.append(info)
                if not findings:
                    ordered = sorted(approved, key=lambda info: info.header_offset)
                    if ordered and ordered[0].header_offset != 0:
                        raise ValueError("prefixed outer ZIP packages are unsupported")
                    for index, info in enumerate(ordered):
                        boundary = ordered[index + 1].header_offset if index + 1 < len(ordered) else directory_offset
                        check_chunks(_package_zip_chunks(stream, info, boundary), info.file_size, info.filename)
        elif p.is_file():
            check_file(p, p.name)
        elif p.is_dir():
            def walk_error(exc):
                raise exc
            for parent, dirs, names in os.walk(p, followlinks=False, onerror=walk_error):
                for name in dirs:
                    child = Path(parent) / name
                    relative = child.relative_to(p).as_posix()
                    if child.is_symlink() or child.is_junction():
                        raise ValueError(f"directory links are not permitted: {relative}")
                    register(relative, 0, True)
                for name in names:
                    child = Path(parent) / name
                    check_file(child, child.relative_to(p).as_posix())
        else:
            raise ValueError("package path is missing or not a regular file/directory")
        if not files:
            raise ValueError("package contains no files")
    except (OSError, ValueError, RuntimeError, NotImplementedError, EOFError, zipfile.BadZipFile, zlib.error) as exc:
        findings.append({"path": str(p), "reason": "scan_blocked", "error": str(exc)})
    forbidden = [f for f in findings if f.get("forbidden")]
    ok = bool(files) and not findings
    result = {"tool": "ROMancer", "version": VERSION, "schema_version": 2,
              "feature": "v22 release boundary scan", "ok": ok, "scope": "package_policy",
              "release_status": "PACKAGE_CHECK_PASSED" if ok else "BLOCKED",
              "provenance": "measured_package_scan", "content_safety_verified": False,
              "path": str(p), "file_count": len(files), "entry_count": entry_count,
              "total_uncompressed_bytes": total_bytes, "files": files, "findings": findings,
              "forbidden_count": len(forbidden), "forbidden_findings": forbidden,
              "limits": {"entries": PACKAGE_MAX_ENTRIES, "member_bytes": PACKAGE_MAX_MEMBER_BYTES,
                         "total_bytes": PACKAGE_MAX_TOTAL_BYTES, "archive_bytes": PACKAGE_MAX_ARCHIVE_BYTES,
                         "directory_bytes": PACKAGE_MAX_DIRECTORY_BYTES},
              "policy": "Checks names, allowed suffixes, common nested archive signatures, ZIP integrity, and resource limits. Reports/evidence/source vault directories are excluded. Allowed suffixes do not prove content safe, original, redistributable, or free of game bytes; manual content review remains required."}
    return write_if(out, result)


def handoff_prompt(project: str, out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    root.mkdir(parents=True, exist_ok=True)
    status = vault_status(project)
    audit = artifact_audit(project)
    handoff = root / "handoff"
    handoff.mkdir(parents=True, exist_ok=True)
    current_facts = {
        "schema": "romancer-current-facts-v30",
        "generated_utc": now_iso(),
        "project_status": status,
        "artifact_audit": audit,
        "rule": "Treat not inspected as not inspected. Do not guess runtime proof.",
    }
    blockers = []
    if not audit.get("ok"):
        blockers.append("Artifact audit has missing, changed, or forbidden files")
    if status.get("missing_directories"):
        blockers.append("Vault directories are missing")
    prompt = f"""Continue this ROMancer project from the attached handoff package.

Rules:
100 percent source-grounded
Do not include ROMs, BIOS files, emulator cores, save states, or copyrighted game assets in release outputs
Treat candidate facts as candidate until file, trace, route, screenshot, memory, or test evidence proves them
Current project: {status.get('project_name')}
System: {status.get('system')}
Goal: {status.get('goal')}

Start by reading:
1. PROJECT_STATUS.json
2. CURRENT_FACTS.json
3. CURRENT_BLOCKERS.json
4. ARTIFACTS_SHA256.txt
5. NEXT_ACTIONS.md

Then run the next safest validation step instead of guessing.
"""
    (handoff / "PROJECT_STATUS.json").write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")
    (handoff / "CURRENT_FACTS.json").write_text(json.dumps(current_facts, indent=2, sort_keys=True), encoding="utf-8")
    (handoff / "CURRENT_BLOCKERS.json").write_text(json.dumps({"blockers": blockers}, indent=2, sort_keys=True), encoding="utf-8")
    ledger = read_jsonish(root / "artifacts" / "artifact_ledger.json", {"artifacts": []}) if (root / "artifacts" / "artifact_ledger.json").exists() else {"artifacts": []}
    hashes = []
    for e in ledger.get("artifacts", []):
        hashes.append(f"{e.get('sha256','unknown')}  {e.get('path','unknown')}")
    (handoff / "ARTIFACTS_SHA256.txt").write_text("\n".join(hashes) + ("\n" if hashes else ""), encoding="utf-8")
    (handoff / "NEXT_ACTIONS.md").write_text("# Next Actions\n\n1. Resolve current blockers\n2. Run boundary scan\n3. Run route or QA matrix based on project stage\n4. Package only safe outputs\n", encoding="utf-8")
    (handoff / "SAFE_CONTINUATION_PROMPT.txt").write_text(prompt, encoding="utf-8")
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v22 handoff prompt", "ok": True, "handoff_dir": str(handoff), "files": [str(x) for x in sorted(handoff.iterdir())]}
    return write_if(out, result)


def _hash_tree(root: Path) -> dict[str, str]:
    if root.is_file() and zipfile.is_zipfile(root):
        out: dict[str, str] = {}
        with zipfile.ZipFile(root, "r") as z:
            for info in sorted(z.infolist(), key=lambda i: i.filename):
                if info.is_dir():
                    continue
                out[info.filename] = hashlib.sha256(z.read(info.filename)).hexdigest()
        return out
    if root.is_file():
        return {root.name: sha256_file(root)}
    out = {}
    for f in sorted(x for x in root.rglob("*") if x.is_file()):
        out[str(f.relative_to(root)).replace(os.sep, "/")] = sha256_file(f)
    return out


def version_diff(a: str, b: str, out: str | None = None) -> dict[str, Any]:
    pa, pb = Path(a), Path(b)
    if not pa.exists() or not pb.exists():
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v22 version diff", "ok": False, "error": "one or both paths do not exist", "a": str(pa), "b": str(pb)})
    ha, hb = _hash_tree(pa), _hash_tree(pb)
    added = sorted(set(hb) - set(ha))
    removed = sorted(set(ha) - set(hb))
    changed = sorted(k for k in set(ha) & set(hb) if ha[k] != hb[k])
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v22 version diff", "ok": True, "a": str(pa), "b": str(pb), "added": added, "removed": removed, "changed": changed, "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)}}
    return write_if(out, result)


def bridge_install_template(backend: str = "generic", out: str | None = None) -> Any:
    backend = backend.lower()
    templates = {
        "mgba": {
            "backend": "mGBA",
            "transport": "script socket or Lua bridge where configured",
            "required_user_inputs": ["emulator path", "content path", "script path or socket endpoint"],
            "capabilities": ["memory read/write where transport is exposed", "breakpoint templates", "scenario snapshots"],
        },
        "mesen2": {
            "backend": "Mesen2",
            "transport": "Lua/debugger scripting where configured",
            "required_user_inputs": ["emulator path", "script output path", "ROM path"],
            "capabilities": ["debugger event templates", "breakpoint templates", "memory watch templates"],
        },
        "blastem": {
            "backend": "BlastEm",
            "transport": "debugger command workflow or trace files",
            "required_user_inputs": ["emulator path", "ROM path", "trace/log path"],
            "capabilities": ["trace import", "breakpoint checklist", "memory-watch plan"],
        },
        "libretro": {
            "backend": "libretro",
            "transport": "existing ROMancer runtime layer",
            "required_user_inputs": ["core path", "content path"],
            "capabilities": ["deterministic input", "state capture", "RAM snapshot when core exposes memory"],
        },
    }
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge install template", "ok": True, "template": templates.get(backend, {"backend": backend, "transport": "manual evidence import", "required_user_inputs": [], "capabilities": ["trace import", "report generation"]})}
    return write_if(out, result)


def bridge_probe(config: str | None = None, out: str | None = None) -> dict[str, Any]:
    rows, errors = [], []
    try:
        cfg = _read(config) if config else {}
        backends = cfg.get("backends", [])
        if not isinstance(backends, list):
            raise ValueError("backends must be a list")
        if not backends:
            backends = [
                {"name": "mgba", "path": os.environ.get("MGBA_PATH", "")},
                {"name": "mesen2", "path": os.environ.get("MESEN2_PATH", "")},
                {"name": "blastem", "path": os.environ.get("BLASTEM_PATH", "")},
                {"name": "libretro", "path": os.environ.get("LIBRETRO_CORE", "")},
            ]
        for backend in backends:
            if not isinstance(backend, dict):
                raise ValueError("backend must be an object")
            name, path = backend.get("name", "unknown"), backend.get("path", "")
            if not isinstance(name, str) or not isinstance(path, str):
                raise ValueError("backend name and path must be strings")
            exists = bool(path) and Path(path).exists()
            discovered = bool(path) and Path(path).is_file()
            rows.append({"backend": name, "path": path, "configured": bool(path),
                         "path_exists": exists, "executable_discovered": discovered,
                         "live_control": False, "handshake_status": "NOT_RUN",
                         "transport_status": "UNIMPLEMENTED", "capabilities": [],
                         "template_capabilities": bridge_install_template(name)["template"]["capabilities"],
                         "provenance": "filesystem_discovery_only"})
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        errors.append(str(exc))
    result = {"tool": "ROMancer", "version": VERSION, "schema_version": 2,
              "feature": "v23 bridge probe", "ok": not errors, "scope": "executable_discovery",
              "status": "BLOCKED" if errors else "DISCOVERY_COMPLETED", "backends": rows,
              "live_control": False, "handshake_status": "NOT_RUN", "validation_errors": errors,
              "provenance": "filesystem_discovery_only",
              "note": "A discovered file is not a validated executable. No transport handshake is implemented or executed, and live control is unverified."}
    return write_if(out, result)


def bridge_read_memory(memory: str, offset: str = "0", length: int = 16, out: str | None = None) -> dict[str, Any]:
    p = Path(memory)
    if not p.exists():
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge read memory", "ok": False, "error": "memory file not found", "memory": str(p)})
    off = int(str(offset), 0)
    data = p.read_bytes()[off:off + length]
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge read memory", "ok": True, "memory": str(p), "offset": off, "length": len(data), "hex": data.hex(" "), "ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in data)}
    return write_if(out, result)


def bridge_watch(addr: str, access: str = "write", backend: str = "generic", out: str | None = None) -> dict[str, Any]:
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge watch", "ok": True, "backend": backend, "address": addr, "access": access, "status": "template", "steps": ["Configure backend path", "Set memory watch or breakpoint", "Capture before state", "Run deterministic input", "Capture after state", "Attach trace/screenshot/RAM evidence"]}
    return write_if(out, result)


def bridge_break(addr: str, access: str = "execute", backend: str = "generic", out: str | None = None) -> dict[str, Any]:
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge break", "ok": True, "backend": backend, "address": addr, "access": access, "status": "template", "commands": [f"break {access} {addr}", "run deterministic scenario", "export trace window", "record registers and stack"]}
    return write_if(out, result)


def bridge_snapshot(target: str, out: str | None = None) -> dict[str, Any]:
    p = Path(target)
    if not p.exists():
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge snapshot", "ok": False, "error": "target not found", "target": str(p)})
    if p.is_file():
        files = [{"path": str(p), "size_bytes": p.stat().st_size, "sha256": sha256_file(p)}]
    else:
        files = [{"path": str(f), "size_bytes": f.stat().st_size, "sha256": sha256_file(f)} for f in sorted(x for x in p.rglob("*") if x.is_file())]
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge snapshot", "ok": True, "target": str(p), "file_count": len(files), "files": files[:200]}
    return write_if(out, result)


def bridge_run_scenario(scenario: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(scenario, {})
    steps = data.get("steps", []) if isinstance(data, dict) else []
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v23 bridge run scenario", "ok": True, "scenario_status": "planned", "step_count": len(steps), "steps": steps, "runtime_status": "not executed unless connected backend evidence is supplied"}
    return write_if(out, result)


def _try_pillow():
    try:
        from PIL import Image  # type: ignore
        return Image
    except Exception:
        return None


def visual_diff(a: str, b: str, out: str | None = None) -> dict[str, Any]:
    pa, pb = Path(a), Path(b)
    if not pa.exists() or not pb.exists():
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v24 visual diff", "ok": False, "error": "one or both image paths missing"})
    Image = _try_pillow()
    if Image:
        ia, ib = Image.open(pa).convert("RGBA"), Image.open(pb).convert("RGBA")
        same_size = ia.size == ib.size
        mismatch = None
        pct = None
        if same_size:
            pix_a, pix_b = ia.tobytes(), ib.tobytes()
            total = ia.size[0] * ia.size[1]
            mismatch = sum(1 for i in range(0, len(pix_a), 4) if pix_a[i:i+4] != pix_b[i:i+4])
            pct = mismatch / total if total else 0
        result = {"tool": "ROMancer", "version": VERSION, "feature": "v24 visual diff", "ok": same_size and mismatch == 0, "a": str(pa), "b": str(pb), "size_a": ia.size, "size_b": ib.size, "same_size": same_size, "mismatched_pixels": mismatch, "mismatch_ratio": pct}
    else:
        result = {"tool": "ROMancer", "version": VERSION, "feature": "v24 visual diff", "ok": sha256_file(pa) == sha256_file(pb), "a": str(pa), "b": str(pb), "mode": "byte hash fallback", "sha256_a": sha256_file(pa), "sha256_b": sha256_file(pb)}
    return write_if(out, result)


def sprite_grid_check(image: str, width: int, height: int, cell_w: int, cell_h: int, cols: int, rows: int, out: str | None = None) -> dict[str, Any]:
    p = Path(image)
    Image = _try_pillow()
    if not p.exists() or not Image:
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v24 sprite grid check", "ok": False, "error": "image missing or Pillow unavailable", "image": str(p)})
    im = Image.open(p)
    actual_w, actual_h = im.size
    expected_w, expected_h = cell_w * cols, cell_h * rows
    checks = {
        "declared_width_ok": actual_w == width,
        "declared_height_ok": actual_h == height,
        "grid_width_ok": actual_w == expected_w,
        "grid_height_ok": actual_h == expected_h,
        "cell_count": cols * rows,
    }
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v24 sprite grid check", "ok": all(v is True or isinstance(v, int) for v in checks.values() if not isinstance(v, str)), "image": str(p), "actual_size": [actual_w, actual_h], "expected_size": [expected_w, expected_h], "cell_size": [cell_w, cell_h], "grid": [cols, rows], "checks": checks}
    return write_if(out, result)


def tile_usage_map(image: str, cell_w: int = 8, cell_h: int = 8, out: str | None = None) -> dict[str, Any]:
    p = Path(image)
    Image = _try_pillow()
    if not p.exists() or not Image:
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v24 tile usage map", "ok": False, "error": "image missing or Pillow unavailable"})
    im = Image.open(p).convert("RGBA")
    w, h = im.size
    tiles = {}
    for y in range(0, h - h % cell_h, cell_h):
        for x in range(0, w - w % cell_w, cell_w):
            tile = im.crop((x, y, x + cell_w, y + cell_h)).tobytes()
            hx = hashlib.sha256(tile).hexdigest()[:16]
            tiles.setdefault(hx, []).append([x, y])
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v24 tile usage map", "ok": True, "image": str(p), "tile_size": [cell_w, cell_h], "unique_tiles": len(tiles), "total_tiles": sum(len(v) for v in tiles.values()), "tiles": [{"hash": k, "count": len(v), "positions": v[:20]} for k, v in sorted(tiles.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:200]]}
    return write_if(out, result)


def palette_consistency(image: str, cell_w: int = 16, cell_h: int = 24, max_colors: int = 16, out: str | None = None) -> dict[str, Any]:
    p = Path(image)
    Image = _try_pillow()
    if not p.exists() or not Image:
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v24 palette consistency", "ok": False, "error": "image missing or Pillow unavailable"})
    im = Image.open(p).convert("RGBA")
    w, h = im.size
    frames = []
    bad = []
    for y in range(0, h - h % cell_h, cell_h):
        for x in range(0, w - w % cell_w, cell_w):
            colors = im.crop((x, y, x + cell_w, y + cell_h)).getcolors(maxcolors=4096) or []
            count = len(colors)
            item = {"x": x, "y": y, "color_count": count, "ok": count <= max_colors}
            frames.append(item)
            if not item["ok"]:
                bad.append(item)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v24 palette consistency", "ok": not bad, "image": str(p), "max_colors": max_colors, "frame_count": len(frames), "bad_frames": bad, "frames": frames[:200]}
    return write_if(out, result)


def exact_text_check(source: str, expected: list[str], label: str, out: str | None = None) -> dict[str, Any]:
    p = Path(source)
    text = p.read_text("utf-8", errors="replace") if p.exists() else source
    rows = [{"text": e, "found": e in text} for e in expected]
    result = {"tool": "ROMancer", "version": VERSION, "feature": label, "ok": all(r["found"] for r in rows), "source": str(source), "checks": rows}
    return write_if(out, result)


def render_oracle(source: str, expected: str | None = None, expected_file: str | None = None, label: str = "v24 text render check", out: str | None = None) -> dict[str, Any]:
    terms: list[str] = []
    if expected_file:
        p = Path(expected_file)
        terms.extend([ln.strip() for ln in p.read_text("utf-8", errors="replace").splitlines() if ln.strip()])
    if expected:
        terms.extend([x.strip() for x in expected.split("|") if x.strip()])
    return exact_text_check(source, terms, label, out)


def portrait_check(image: str, width: int = 40, height: int = 40, max_colors: int = 16, out: str | None = None) -> dict[str, Any]:
    p = Path(image)
    Image = _try_pillow()
    if not p.exists() or not Image:
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v24 portrait check", "ok": False, "error": "image missing or Pillow unavailable"})
    im = Image.open(p).convert("RGBA")
    colors = im.getcolors(maxcolors=100000) or []
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v24 portrait check", "ok": im.size == (width, height) and len(colors) <= max_colors, "image": str(p), "actual_size": list(im.size), "expected_size": [width, height], "color_count": len(colors), "max_colors": max_colors}
    return write_if(out, result)


def sdk_create(project: str, game: str = "generic", system: str = "unknown", out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    sdk_dir = root / "sdk"
    sdk_dir.mkdir(parents=True, exist_ok=True)
    profile = {
        "schema": "romancer-game-sdk-v30",
        "tool": "ROMancer",
        "version": VERSION,
        "game": game,
        "system": system,
        "fact_policy": "Every game-specific claim must be verified, candidate, contradicted, or not inspected",
        "sections": {
            "maps": [],
            "events": [],
            "text": [],
            "battles": [],
            "characters": [],
            "save": [],
            "audio": [],
        },
        "status_vocab": ["verified", "high-confidence", "candidate", "contradicted", "not inspected"],
    }
    if "ff6" in game.lower() or "final fantasy" in game.lower():
        profile["starter_assumptions"] = ["SNES map/event/text/battle/save layers must be independently verified against the target ROM"]
    if "shadowrun" in game.lower():
        profile["starter_assumptions"] = ["Scenario routing and Japanese text checks require runtime route evidence"]
    path = sdk_dir / "game_sdk.json"
    write_json(str(path), profile)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v25 SDK create", "ok": True, "sdk": str(path), "profile": profile}
    return write_if(out, result)


def sdk_audit(sdk: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(sdk, {})
    required = ["schema", "game", "system", "sections", "status_vocab"]
    missing = [k for k in required if k not in data]
    sections = data.get("sections", {}) if isinstance(data, dict) else {}
    required_sections = ["maps", "events", "text", "battles", "characters", "save", "audio"]
    missing_sections = [k for k in required_sections if k not in sections]
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v25 SDK audit", "ok": not missing and not missing_sections, "missing_fields": missing, "missing_sections": missing_sections, "section_counts": {k: len(v) if isinstance(v, list) else 0 for k, v in sections.items()}}
    return write_if(out, result)


def sdk_report(sdk: str, section: str, out: str | None = None) -> Any:
    data = read_jsonish(sdk, {})
    rows = data.get("sections", {}).get(section, []) if isinstance(data, dict) else []
    result = {"tool": "ROMancer", "version": VERSION, "feature": f"v25 {section} report", "ok": True, "game": data.get("game", "unknown") if isinstance(data, dict) else "unknown", "section": section, "count": len(rows), "records": rows}
    return write_if(out, result)


def sdk_export(sdk: str, out: str | None = None) -> Any:
    data = read_jsonish(sdk, {})
    lines = ["# ROMancer Game SDK Export", "", f"Game: {data.get('game', 'unknown')}", f"System: {data.get('system', 'unknown')}", ""]
    for section, rows in data.get("sections", {}).items():
        lines.append(f"## {section}")
        if not rows:
            lines.append("No records")
        else:
            for i, row in enumerate(rows, 1):
                lines.append(f"{i}. {json.dumps(row, sort_keys=True)}")
        lines.append("")
    text = "\n".join(lines)
    return write_if(out, text)


def alloc_space(binary: str, min_len: int = 32, byte_values: str = "00,ff", limit: int = 50, out: str | None = None) -> dict[str, Any]:
    p = Path(binary)
    if not p.exists():
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v26 free-space allocator", "ok": False, "error": "file not found"})
    data = p.read_bytes()
    vals = {int(x.strip(), 16) for x in byte_values.split(",") if x.strip()}
    runs = []
    i = 0
    while i < len(data):
        if data[i] in vals:
            j = i + 1
            while j < len(data) and data[j] == data[i]:
                j += 1
            if j - i >= min_len:
                runs.append({"offset": i, "hex_offset": hex(i), "length": j - i, "byte": f"{data[i]:02X}"})
                if len(runs) >= limit:
                    break
            i = j
        else:
            i += 1
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v26 free-space allocator", "ok": True, "file": str(p), "min_len": min_len, "runs": runs, "count": len(runs)}
    return write_if(out, result)


def hook_plan(system: str, source_addr: str, target_addr: str, reason: str = "", out: str | None = None) -> dict[str, Any]:
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v26 hook plan", "ok": True, "system": system, "source_addr": source_addr, "target_addr": target_addr, "reason": reason, "required_checks": ["Confirm source bytes before patching", "Confirm target free space reservation", "Generate rollback patch", "Run route and QA matrix after patch"], "status": "plan only"}
    return write_if(out, result)


def asm_build(source: str, out_dir: str = "build", assembler: str = "none", out: str | None = None) -> dict[str, Any]:
    src = Path(source)
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v26 asm build", "ok": False, "error": "source missing"})
    dst = od / src.name
    shutil.copy2(src, dst)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v26 asm build", "ok": True, "assembler": assembler, "source": str(src), "copied_to": str(dst), "status": "source staged; external assembler not invoked unless configured"}
    return write_if(out, result)


def patch_stack(manifest: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    patches = data.get("patches", []) if isinstance(data, dict) else []
    ordered = sorted(patches, key=lambda p: (p.get("priority", 100), p.get("name", "")))
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v26 patch stack", "ok": True, "patch_count": len(ordered), "ordered_patches": ordered}
    return write_if(out, result)


def _ranges_from_manifest(path: str | Path) -> list[dict[str, Any]]:
    data = read_jsonish(path, {})
    ranges = []
    if isinstance(data, dict):
        for r in data.get("ranges", data.get("changes", [])):
            try:
                start = int(str(r.get("offset", r.get("start", 0))), 0)
                length = int(str(r.get("length", 1)), 0)
                ranges.append({"source": str(path), "start": start, "end": start + length, "label": r.get("label", r.get("name", "change"))})
            except Exception:
                pass
    return ranges


def patch_collision_check(manifest: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    ranges: list[dict[str, Any]] = []
    if isinstance(data, dict) and "patches" in data:
        for p in data["patches"]:
            if "ranges" in p:
                for r in p["ranges"]:
                    try:
                        start = int(str(r.get("offset", r.get("start", 0))), 0)
                        length = int(str(r.get("length", 1)), 0)
                        ranges.append({"source": p.get("name", "patch"), "start": start, "end": start + length, "label": r.get("label", "change")})
                    except Exception:
                        pass
    else:
        ranges = _ranges_from_manifest(manifest)
    collisions = []
    for i, a in enumerate(ranges):
        for b in ranges[i+1:]:
            if max(a["start"], b["start"]) < min(a["end"], b["end"]):
                collisions.append({"a": a, "b": b})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v26 patch collision check", "ok": not collisions, "range_count": len(ranges), "collisions": collisions}
    return write_if(out, result)


def rollback_build(original: str, modified: str, out_patch: str, out: str | None = None) -> dict[str, Any]:
    result = create_ips(modified, original, out_patch)
    wrapped = {"tool": "ROMancer", "version": VERSION, "feature": "v26 rollback build", "ok": True, "rollback_patch": out_patch, "base_result": result}
    return write_if(out, wrapped)


def patch_explain(original: str, modified: str, out: str | None = None) -> dict[str, Any]:
    diff = byte_diff(original, modified)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v26 patch explain", "ok": True, "diff": diff, "note": "Byte-level explanation only. Semantic meaning requires game SDK and trace evidence."}
    return write_if(out, result)


def route_map(manifest: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    nodes = data.get("nodes", data.get("locations", [])) if isinstance(data, dict) else []
    edges = data.get("edges", data.get("routes", [])) if isinstance(data, dict) else []
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v27 route map", "ok": True, "node_count": len(nodes), "edge_count": len(edges), "nodes": nodes, "edges": edges}
    return write_if(out, result)


def route_next(manifest: str, current: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    edges = data.get("edges", data.get("routes", [])) if isinstance(data, dict) else []
    nexts = [e for e in edges if str(e.get("from", e.get("source", ""))) == current]
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v27 route next", "ok": True, "current": current, "next": nexts}
    return write_if(out, result)


def route_run(manifest: str, evidence: str | None = None, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    ev = read_jsonish(evidence, {}) if evidence else {}
    steps = data.get("steps", data.get("route", [])) if isinstance(data, dict) else []
    rows = []
    for i, step in enumerate(steps, 1):
        key = step.get("id", str(i)) if isinstance(step, dict) else str(i)
        proof = ev.get(str(key)) if isinstance(ev, dict) else None
        rows.append({"step": step, "status": "verified" if proof else "not inspected", "evidence": proof or None})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v27 route run", "ok": all(r["status"] == "verified" for r in rows) if rows else False, "step_count": len(rows), "steps": rows}
    return write_if(out, result)


def cutscene_lock_check(manifest: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    scenes = data.get("cutscenes", []) if isinstance(data, dict) else []
    rows = []
    for sc in scenes:
        player_locked = bool(sc.get("player_locked", False))
        actors_ok = all(a.get("speaker") or a.get("actor") for a in sc.get("actions", []))
        rows.append({"scene": sc.get("id", sc.get("name", "unknown")), "player_locked": player_locked, "actor_continuity_ok": actors_ok, "ok": player_locked and actors_ok})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v27 cutscene lock check", "ok": all(r["ok"] for r in rows) if rows else False, "scenes": rows}
    return write_if(out, result)


def softlock_scan(manifest: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    nodes = {str(n.get("id", n)) for n in data.get("nodes", data.get("locations", []))} if isinstance(data, dict) else set()
    edges = data.get("edges", data.get("routes", [])) if isinstance(data, dict) else []
    outgoing = {str(e.get("from", e.get("source", ""))) for e in edges}
    terminal_ok = {str(x) for x in data.get("valid_terminals", [])} if isinstance(data, dict) else set()
    dead = sorted(n for n in nodes if n not in outgoing and n not in terminal_ok)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v27 softlock scan", "ok": not dead, "dead_end_nodes": dead, "node_count": len(nodes), "edge_count": len(edges)}
    return write_if(out, result)


def optional_area_check(manifest: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    areas = data.get("optional_areas", []) if isinstance(data, dict) else []
    rows = []
    for a in areas:
        rows.append({"area": a.get("name", a.get("id", "unknown")), "entry_condition": a.get("entry_condition", "unknown"), "reward_or_reason": a.get("reward", a.get("reason", "")), "status": a.get("status", "not inspected")})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v27 optional area check", "ok": all(str(r["status"]).lower() in STATUS_PASS for r in rows) if rows else False, "areas": rows}
    return write_if(out, result)


def natural_route_validate(manifest: str, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {})
    required = ["clean_start", "party_state", "menu", "battle", "save_load", "route_completion"]
    checks = data.get("checks", {}) if isinstance(data, dict) else {}
    rows = []
    for key in required:
        status = str(checks.get(key, "not inspected")).lower() if isinstance(checks, dict) else "not inspected"
        rows.append({"check": key, "status": status, "ok": status in STATUS_PASS})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v27 natural route validation", "ok": all(r["ok"] for r in rows), "checks": rows}
    return write_if(out, result)


def _matrix(name: str, manifest: str | None = None, out: str | None = None) -> dict[str, Any]:
    data = read_jsonish(manifest, {}) if manifest else {}
    entries = data.get("entries", data.get("checks", [])) if isinstance(data, dict) else []
    if isinstance(entries, dict):
        entries = [{"name": k, "status": v} for k, v in entries.items()]
    rows = []
    for e in entries:
        status = str(e.get("status", "not inspected")).lower()
        rows.append({"name": e.get("name", e.get("id", "unnamed")), "status": status, "required": bool(e.get("required", True)), "ok": status in STATUS_PASS})
    ok = all((not r["required"]) or r["ok"] for r in rows) if rows else False
    result = {"tool": "ROMancer", "version": VERSION, "feature": f"v28 {name}", "ok": ok, "entry_count": len(rows), "checks": rows}
    return write_if(out, result)


def demo_certify(manifest: str, out: str | None = None) -> dict[str, Any]:
    rows, errors = [], []
    try:
        data = _read(manifest)
        gates = data.get("gates", data.get("checks"))
        if isinstance(gates, dict):
            gates = [{"name": k, "status": v, "required": True} for k, v in gates.items()]
        gates = _validate_gates(gates, {"assertion"}, "assertion")
        for gate in gates:
            row = {"name": gate["name"], "required": gate["required"], "kind": gate["kind"],
                   "provenance": "imported_assertion", "measured": False,
                   "ok": False, "gate_status": "BLOCKED"}
            try:
                assertion = dict(gate)
                value = assertion.get("status")
                # Preserve legacy demo spellings, explicitly as supplied assertions.
                if isinstance(value, str):
                    aliases = {"passed": "PASS", "verified": "PASS", "fixed": "PASS", "ok": "PASS",
                               "failed": "FAIL", "broken": "FAIL", "error": "BLOCKED",
                               "not inspected": "NOT_RUN", "not run": "NOT_RUN"}
                    assertion["status"] = aliases.get(value.lower(), value)
                status = _assertion_status(assertion)
                row.update(status=status, gate_status=status, ok=status == "PASS")
            except ValueError as exc:
                row["error"] = str(exc)
            rows.append(row)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        errors.append(str(exc))
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v28 demo gate evaluation",
              **_gate_summary(rows, errors)}
    return write_if(out, result)


def studio(project: str, out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    status = vault_status(project)
    audit = artifact_audit(project)
    dashboard = {"tool": "ROMancer", "version": VERSION, "feature": "v29 studio dashboard", "ok": True, "project_status": status, "artifact_audit": audit}
    write_json(str(reports / "studio_dashboard.json"), dashboard)
    html = f"<html><body><h1>ROMancer Studio</h1><p>Project: {status.get('project_name')}</p><p>Version: {VERSION}</p><p>Artifacts: {status.get('artifact_count')}</p><p>Artifact audit OK: {audit.get('ok')}</p></body></html>"
    (reports / "studio_dashboard.html").write_text(html, encoding="utf-8")
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v29 studio", "ok": True, "dashboard_json": str(reports / "studio_dashboard.json"), "dashboard_html": str(reports / "studio_dashboard.html")}
    return write_if(out, result)


def studio_build(project: str, out_dir: str = "studio_build", out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    studio(project)
    copied = []
    for src in [root / "romancer_project.json", root / "reports" / "studio_dashboard.json", root / "reports" / "studio_dashboard.html"]:
        if src.exists():
            dst = od / src.name
            shutil.copy2(src, dst)
            copied.append(str(dst))
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v29 studio build", "ok": True, "out_dir": str(od), "files": copied}
    return write_if(out, result)


def studio_report(project: str, out: str | None = None) -> Any:
    status = vault_status(project)
    text = "\n".join([
        "# ROMancer Studio Report",
        "",
        f"Project: {status.get('project_name')}",
        f"System: {status.get('system')}",
        f"Goal: {status.get('goal')}",
        f"Artifact count: {status.get('artifact_count')}",
        f"Vault OK: {status.get('ok')}",
        "",
    ])
    return write_if(out, text)


def qa_board(project: str, out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    qa = root / "qa"
    rows = []
    if qa.exists():
        for f in sorted(qa.glob("*.json")):
            data = read_jsonish(f, {})
            rows.append({"file": str(f), "ok": data.get("ok"), "feature": data.get("feature", f.stem)})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v29 QA board", "ok": True, "project": str(root), "rows": rows}
    return write_if(out, result)


def visual_report(project: str, out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    reports = []
    for f in sorted(root.rglob("*visual*.json")):
        data = read_jsonish(f, {})
        reports.append({"file": str(f), "ok": data.get("ok"), "mismatched_pixels": data.get("mismatched_pixels")})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v29 visual report", "ok": True, "reports": reports}
    return write_if(out, result)


def dashboard_export(project: str, out: str | None = None) -> dict[str, Any]:
    result = studio(project)
    if out:
        src = Path(result["dashboard_json"])
        shutil.copy2(src, out)
        result["exported_to"] = out
    return result


def v30_new_project(project: str, name: str = "", system: str = "", goal: str = "", out: str | None = None) -> dict[str, Any]:
    res = vault_init(project, name=name, system=system, goal=goal)
    sdk = sdk_create(project, game=name or Path(project).name, system=system or "unknown")
    hand = handoff_prompt(project)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v30 new project", "ok": True, "vault": res, "sdk": sdk.get("sdk"), "handoff": hand.get("handoff_dir")}
    return write_if(out, result)


def v30_import_source(project: str, source: str, kind: str = "source", out: str | None = None) -> dict[str, Any]:
    root = Path(project)
    src = Path(source)
    if not src.exists():
        return write_if(out, {"tool": "ROMancer", "version": VERSION, "feature": "v30 import source", "ok": False, "error": "source not found"})
    dst_dir = root / "sources"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if src.is_file():
        shutil.copy2(src, dst)
        art = artifact_add(project, str(dst), kind=kind, reason="v30 source import", status="not inspected")
    else:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        art = {"directory": str(dst), "status": "copied"}
    scan = release_boundary_scan(dst)
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v30 import source", "ok": True, "source": str(src), "destination": str(dst), "artifact": art, "boundary_scan": scan}
    return write_if(out, result)


def certify_release(root: str, out: str | None = None) -> dict[str, Any]:
    boundary = release_boundary_scan(root)
    result = {"tool": "ROMancer", "version": VERSION, "schema_version": 2,
              "feature": "v30 package check", "ok": boundary["ok"],
              "release_status": boundary["release_status"], "scope": "package_policy",
              "provenance": "measured_package_scan", "content_safety_verified": False,
              "boundary_scan": boundary,
              "required_followups": ["Review content provenance and redistribution permission; this check does not establish full-game correctness or release approval"]
              + ([] if boundary["ok"] else ["Resolve all package scan findings before publishing"])}
    return write_if(out, result)


def v30_status(project: str, out: str | None = None) -> dict[str, Any]:
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v30 status", "ok": True, "vault": vault_status(project), "artifact_audit": artifact_audit(project), "qa_board": qa_board(project)}
    return write_if(out, result)


def v30_capabilities(out: str | None = None) -> dict[str, Any]:
    caps = {
        "v22": ["vault-init", "vault-status", "artifact-add", "artifact-audit", "artifact-lineage", "handoff-prompt", "release-boundary-scan", "version-diff"],
        "v23": ["bridge-install-template", "bridge-probe-v30", "bridge-read-memory", "bridge-watch-v30", "bridge-break-v30", "bridge-snapshot-v30", "bridge-run-scenario-v30"],
        "v24": ["visual-diff", "sprite-grid-check", "tile-usage-map", "palette-consistency", "text-render-check", "menu-oracle", "battle-text-oracle", "portrait-check"],
        "v25": ["sdk-create", "sdk-audit", "sdk-map-report", "sdk-event-report", "sdk-text-report", "sdk-battle-report", "sdk-save-report", "sdk-export"],
        "v26": ["alloc-space", "hook-plan", "asm-build", "patch-stack-v30", "patch-collision-check-v30", "rollback-build", "patch-explain-v30"],
        "v27": ["route-map", "route-next", "route-run", "cutscene-lock-check", "softlock-scan", "optional-area-check", "natural-route-validate"],
        "v28": ["qa-matrix", "menu-matrix", "battle-matrix", "economy-matrix", "save-load-matrix", "boss-matrix", "random-battle-matrix", "text-matrix", "demo-certify"],
        "v29": ["studio", "studio-build", "studio-report", "dashboard-export", "qa-board", "visual-report"],
        "v30": ["v30-new-project", "v30-import-source", "v30-build-sdk", "certify-release", "v30-status", "v30-capabilities", "v30-self-test"],
    }
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v30 capabilities", "ok": True, "capabilities": caps, "policy": "Unsupported runtime control is reported as not executed instead of guessed."}
    return write_if(out, result)


def v30_self_test(out: str | None = None) -> dict[str, Any]:
    tests = []
    with tempfile.TemporaryDirectory(prefix="romancer_v30_") as td0:
        td = Path(td0)
        proj = td / "Project"
        vi = vault_init(str(proj), name="Fixture", system="SNES", goal="test")
        tests.append({"name": "v22 vault init", "ok": vi.get("ok") and (proj / "romancer_project.json").exists()})
        sample = td / "sample.txt"; sample.write_text("Start Menu Attack Save", encoding="utf-8")
        aa = artifact_add(str(proj), str(sample), kind="txt", reason="fixture", status="verified")
        tests.append({"name": "v22 artifact add", "ok": aa.get("ok")})
        tests.append({"name": "v22 artifact audit", "ok": artifact_audit(str(proj)).get("ok")})
        tests.append({"name": "v22 handoff", "ok": handoff_prompt(str(proj)).get("ok")})
        mem = td / "mem.bin"; mem.write_bytes(bytes(range(64)))
        tests.append({"name": "v23 read memory", "ok": bridge_read_memory(str(mem), "0x10", 4).get("hex") == "10 11 12 13"})
        Image = _try_pillow()
        if Image:
            im = Image.new("RGBA", (32, 48), (0, 0, 0, 0)); img = td / "sprite.png"; im.save(img)
            tests.append({"name": "v24 sprite grid", "ok": sprite_grid_check(str(img), 32, 48, 16, 24, 2, 2).get("ok")})
            tests.append({"name": "v24 visual diff", "ok": visual_diff(str(img), str(img)).get("ok")})
        else:
            tests.append({"name": "v24 Pillow optional", "ok": True})
        sdk = sdk_create(str(proj), "Fixture", "SNES")
        tests.append({"name": "v25 sdk create/audit", "ok": sdk_audit(sdk["sdk"]).get("ok")})
        binf = td / "rom.bin"; binf.write_bytes(b"A" * 16 + b"\xff" * 64 + b"B" * 16)
        tests.append({"name": "v26 alloc space", "ok": alloc_space(str(binf), 32).get("count", 0) >= 1})
        stack = td / "stack.json"; stack.write_text(json.dumps({"patches": [{"name": "a", "priority": 2}, {"name": "b", "priority": 1}]}), encoding="utf-8")
        tests.append({"name": "v26 patch stack", "ok": patch_stack(str(stack))["ordered_patches"][0]["name"] == "b"})
        route = td / "route.json"; route.write_text(json.dumps({"nodes": [{"id": "start"}, {"id": "end"}], "edges": [{"from": "start", "to": "end"}], "valid_terminals": ["end"], "checks": {"clean_start": "verified", "party_state": "verified", "menu": "verified", "battle": "verified", "save_load": "verified", "route_completion": "verified"}}), encoding="utf-8")
        tests.append({"name": "v27 softlock scan", "ok": softlock_scan(str(route)).get("ok")})
        tests.append({"name": "v27 natural route", "ok": natural_route_validate(str(route)).get("ok")})
        qa = td / "qa.json"; qa.write_text(json.dumps({"gates": {"menu": "verified", "battle": "verified"}}), encoding="utf-8")
        tests.append({"name": "v28 demo certify", "ok": demo_certify(str(qa)).get("ok")})
        tests.append({"name": "v29 studio", "ok": studio(str(proj)).get("ok")})
        tests.append({"name": "v30 certify release blocks ROM", "ok": not certify_release(str(binf)).get("ok")})
        tests.append({"name": "v30 capabilities", "ok": bool(v30_capabilities().get("capabilities"))})
    result = {"tool": "ROMancer", "version": VERSION, "feature": "v30 self-test", "ok": all(t["ok"] for t in tests), "tests": tests}
    return write_if(out, result)


def add_v22_30_parsers(sub):
    # v22
    s = sub.add_parser("vault-init", help="[v22] Create a project vault with manifest, artifact ledger, QA, route, SDK, and handoff folders"); s.add_argument("project"); s.add_argument("--name", default=""); s.add_argument("--system", default=""); s.add_argument("--goal", default=""); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("vault-status", help="[v22] Summarize vault health and artifact counts"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("artifact-add", help="[v22] Add a file to the artifact ledger with checksum and status"); s.add_argument("project"); s.add_argument("path"); s.add_argument("--kind", default="artifact"); s.add_argument("--reason", default=""); s.add_argument("--status", default="not inspected"); s.add_argument("--parent", default=""); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("artifact-audit", help="[v22] Verify artifact existence, checksums, and forbidden suffixes"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("artifact-lineage", help="[v22] Export artifact parent graph"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("handoff-prompt", help="[v22] Generate a safe continuation handoff folder and prompt"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("release-boundary-scan", help="[v22] Scan a folder or ZIP for forbidden ROM/BIOS/save payloads"); s.add_argument("root"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("version-diff", help="[v22] Compare two folders, files, or ZIPs by content hashes"); s.add_argument("a"); s.add_argument("b"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    # v23
    s = sub.add_parser("bridge-install-template", help="[v23] Emit backend bridge configuration template"); s.add_argument("--backend", default="generic"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("bridge-probe-v30", help="[v23] Probe configured bridge paths without claiming unsupported live control"); s.add_argument("--config"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("bridge-read-memory", help="[v23] Read bytes from an exported RAM/memory snapshot"); s.add_argument("memory"); s.add_argument("--offset", default="0"); s.add_argument("--length", type=int, default=16); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("bridge-watch-v30", help="[v23] Produce a memory watch plan"); s.add_argument("addr"); s.add_argument("--access", default="write"); s.add_argument("--backend", default="generic"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("bridge-break-v30", help="[v23] Produce a breakpoint plan"); s.add_argument("addr"); s.add_argument("--access", default="execute"); s.add_argument("--backend", default="generic"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("bridge-snapshot-v30", help="[v23] Hash an evidence file or folder snapshot"); s.add_argument("target"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("bridge-run-scenario-v30", help="[v23] Plan a bridge scenario from JSON evidence"); s.add_argument("scenario"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    # v24
    s = sub.add_parser("visual-diff", help="[v24] Pixel or hash compare two images"); s.add_argument("a"); s.add_argument("b"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("sprite-grid-check", help="[v24] Validate native sprite-sheet size and grid"); s.add_argument("image"); s.add_argument("--width", type=int, required=True); s.add_argument("--height", type=int, required=True); s.add_argument("--cell-w", type=int, required=True); s.add_argument("--cell-h", type=int, required=True); s.add_argument("--cols", type=int, required=True); s.add_argument("--rows", type=int, required=True); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("tile-usage-map", help="[v24] Hash repeated image tiles"); s.add_argument("image"); s.add_argument("--cell-w", type=int, default=8); s.add_argument("--cell-h", type=int, default=8); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("palette-consistency", help="[v24] Check per-frame color-count limits"); s.add_argument("image"); s.add_argument("--cell-w", type=int, default=16); s.add_argument("--cell-h", type=int, default=24); s.add_argument("--max-colors", type=int, default=16); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    for cmd, label in [("text-render-check", "v24 text render check"), ("menu-oracle", "v24 menu oracle"), ("battle-text-oracle", "v24 battle text oracle")]:
        s = sub.add_parser(cmd, help=f"[{label.split()[0]}] Exact text oracle"); s.add_argument("source"); s.add_argument("--expected"); s.add_argument("--expected-file"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("portrait-check", help="[v24] Validate portrait image dimensions and palette count"); s.add_argument("image"); s.add_argument("--width", type=int, default=40); s.add_argument("--height", type=int, default=40); s.add_argument("--max-colors", type=int, default=16); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    # v25
    s = sub.add_parser("sdk-create", help="[v25] Create a game SDK scaffold"); s.add_argument("project"); s.add_argument("--game", default="generic"); s.add_argument("--system", default="unknown"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("sdk-audit", help="[v25] Audit a game SDK JSON file"); s.add_argument("sdk"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    for cmd, section in [("sdk-map-report", "maps"), ("sdk-event-report", "events"), ("sdk-text-report", "text"), ("sdk-battle-report", "battles"), ("sdk-save-report", "save")]:
        s = sub.add_parser(cmd, help=f"[v25] Report SDK section {section}"); s.add_argument("sdk"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("sdk-export", help="[v25] Export SDK as Markdown"); s.add_argument("sdk"); s.add_argument("--out", required=True); s.add_argument("--json", action="store_true")
    # v26
    s = sub.add_parser("alloc-space", help="[v26] Find free-space runs in a binary"); s.add_argument("binary"); s.add_argument("--min-len", type=int, default=32); s.add_argument("--byte-values", default="00,ff"); s.add_argument("--limit", type=int, default=50); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("hook-plan", help="[v26] Build a conservative hook plan"); s.add_argument("--system", required=True); s.add_argument("--source-addr", required=True); s.add_argument("--target-addr", required=True); s.add_argument("--reason", default=""); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("asm-build", help="[v26] Stage assembly source and report external assembler status"); s.add_argument("source"); s.add_argument("--out-dir", default="build"); s.add_argument("--assembler", default="none"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("patch-stack-v30", help="[v26] Order patch stack from manifest"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("patch-collision-check-v30", help="[v26] Check patch range collisions from manifest"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("rollback-build", help="[v26] Build IPS rollback from modified file to original file"); s.add_argument("original"); s.add_argument("modified"); s.add_argument("--out-patch", required=True); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("patch-explain-v30", help="[v26] Explain byte changes between original and modified files"); s.add_argument("original"); s.add_argument("modified"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    # v27
    s = sub.add_parser("route-map", help="[v27] Summarize route graph manifest"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("route-next", help="[v27] List next route edges from a node"); s.add_argument("manifest"); s.add_argument("--current", required=True); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("route-run", help="[v27] Mark route steps verified only when evidence is supplied"); s.add_argument("manifest"); s.add_argument("--evidence"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("cutscene-lock-check", help="[v27] Check cutscene lock and actor continuity fields"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("softlock-scan", help="[v27] Detect dead-end route nodes not declared valid terminals"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("optional-area-check", help="[v27] Audit optional-area access records"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("natural-route-validate", help="[v27] Validate clean-start, menu, battle, save/load, and completion checks"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    # v28
    for cmd, name in [("qa-matrix", "QA matrix"), ("menu-matrix", "menu matrix"), ("battle-matrix", "battle matrix"), ("economy-matrix", "economy matrix"), ("save-load-matrix", "save load matrix"), ("boss-matrix", "boss matrix"), ("random-battle-matrix", "random battle matrix"), ("text-matrix", "text matrix")]:
        s = sub.add_parser(cmd, help=f"[v28] Evaluate {name}"); s.add_argument("--manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("demo-certify", help="[v28] Certify demo gates from a manifest"); s.add_argument("manifest"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    # v29
    s = sub.add_parser("studio", help="[v29] Build project studio dashboard"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("studio-build", help="[v29] Copy studio dashboard files to an output folder"); s.add_argument("project"); s.add_argument("--out-dir", default="studio_build"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("studio-report", help="[v29] Write human-readable studio report"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("dashboard-export", help="[v29] Export dashboard JSON"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("qa-board", help="[v29] Summarize QA report JSON files"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("visual-report", help="[v29] Summarize visual diff reports"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    # v30
    s = sub.add_parser("v30-new-project", help="[v30] Create project vault plus SDK and handoff scaffold"); s.add_argument("project"); s.add_argument("--name", default=""); s.add_argument("--system", default=""); s.add_argument("--goal", default=""); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("v30-import-source", help="[v30] Copy source into vault and add artifact record when safe"); s.add_argument("project"); s.add_argument("source"); s.add_argument("--kind", default="source"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("v30-build-sdk", help="[v30] Alias for SDK creation"); s.add_argument("project"); s.add_argument("--game", default="generic"); s.add_argument("--system", default="unknown"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("certify-release", help="[v30] Certify a release folder or ZIP boundary"); s.add_argument("root"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("v30-status", help="[v30] Combined vault, artifact, and QA status"); s.add_argument("project"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("v30-capabilities", help="[v30] List v22 through v30 capabilities"); s.add_argument("--out"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("v30-self-test", help="[v30] Run v22 through v30 deterministic integration self-test"); s.add_argument("--out"); s.add_argument("--json", action="store_true")


def dispatch_v22_30(args):
    c = getattr(args, "cmd", "")
    if c == "vault-init": return True, vault_init(args.project, args.name, args.system, args.goal, args.out)
    if c == "vault-status": return True, vault_status(args.project, args.out)
    if c == "artifact-add": return True, artifact_add(args.project, args.path, args.kind, args.reason, args.status, args.parent, args.out)
    if c == "artifact-audit": return True, artifact_audit(args.project, args.out)
    if c == "artifact-lineage": return True, artifact_lineage(args.project, args.out)
    if c == "handoff-prompt": return True, handoff_prompt(args.project, args.out)
    if c == "release-boundary-scan": return True, release_boundary_scan(args.root, args.out)
    if c == "version-diff": return True, version_diff(args.a, args.b, args.out)
    if c == "bridge-install-template": return True, bridge_install_template(args.backend, args.out)
    if c == "bridge-probe-v30": return True, bridge_probe(args.config, args.out)
    if c == "bridge-read-memory": return True, bridge_read_memory(args.memory, args.offset, args.length, args.out)
    if c == "bridge-watch-v30": return True, bridge_watch(args.addr, args.access, args.backend, args.out)
    if c == "bridge-break-v30": return True, bridge_break(args.addr, args.access, args.backend, args.out)
    if c == "bridge-snapshot-v30": return True, bridge_snapshot(args.target, args.out)
    if c == "bridge-run-scenario-v30": return True, bridge_run_scenario(args.scenario, args.out)
    if c == "visual-diff": return True, visual_diff(args.a, args.b, args.out)
    if c == "sprite-grid-check": return True, sprite_grid_check(args.image, args.width, args.height, args.cell_w, args.cell_h, args.cols, args.rows, args.out)
    if c == "tile-usage-map": return True, tile_usage_map(args.image, args.cell_w, args.cell_h, args.out)
    if c == "palette-consistency": return True, palette_consistency(args.image, args.cell_w, args.cell_h, args.max_colors, args.out)
    if c == "text-render-check": return True, render_oracle(args.source, args.expected, args.expected_file, "v24 text render check", args.out)
    if c == "menu-oracle": return True, render_oracle(args.source, args.expected, args.expected_file, "v24 menu oracle", args.out)
    if c == "battle-text-oracle": return True, render_oracle(args.source, args.expected, args.expected_file, "v24 battle text oracle", args.out)
    if c == "portrait-check": return True, portrait_check(args.image, args.width, args.height, args.max_colors, args.out)
    if c == "sdk-create": return True, sdk_create(args.project, args.game, args.system, args.out)
    if c == "sdk-audit": return True, sdk_audit(args.sdk, args.out)
    if c == "sdk-map-report": return True, sdk_report(args.sdk, "maps", args.out)
    if c == "sdk-event-report": return True, sdk_report(args.sdk, "events", args.out)
    if c == "sdk-text-report": return True, sdk_report(args.sdk, "text", args.out)
    if c == "sdk-battle-report": return True, sdk_report(args.sdk, "battles", args.out)
    if c == "sdk-save-report": return True, sdk_report(args.sdk, "save", args.out)
    if c == "sdk-export": return True, sdk_export(args.sdk, args.out)
    if c == "alloc-space": return True, alloc_space(args.binary, args.min_len, args.byte_values, args.limit, args.out)
    if c == "hook-plan": return True, hook_plan(args.system, args.source_addr, args.target_addr, args.reason, args.out)
    if c == "asm-build": return True, asm_build(args.source, args.out_dir, args.assembler, args.out)
    if c == "patch-stack-v30": return True, patch_stack(args.manifest, args.out)
    if c == "patch-collision-check-v30": return True, patch_collision_check(args.manifest, args.out)
    if c == "rollback-build": return True, rollback_build(args.original, args.modified, args.out_patch, args.out)
    if c == "patch-explain-v30": return True, patch_explain(args.original, args.modified, args.out)
    if c == "route-map": return True, route_map(args.manifest, args.out)
    if c == "route-next": return True, route_next(args.manifest, args.current, args.out)
    if c == "route-run": return True, route_run(args.manifest, args.evidence, args.out)
    if c == "cutscene-lock-check": return True, cutscene_lock_check(args.manifest, args.out)
    if c == "softlock-scan": return True, softlock_scan(args.manifest, args.out)
    if c == "optional-area-check": return True, optional_area_check(args.manifest, args.out)
    if c == "natural-route-validate": return True, natural_route_validate(args.manifest, args.out)
    if c == "qa-matrix": return True, _matrix("QA matrix", args.manifest, args.out)
    if c == "menu-matrix": return True, _matrix("menu matrix", args.manifest, args.out)
    if c == "battle-matrix": return True, _matrix("battle matrix", args.manifest, args.out)
    if c == "economy-matrix": return True, _matrix("economy matrix", args.manifest, args.out)
    if c == "save-load-matrix": return True, _matrix("save load matrix", args.manifest, args.out)
    if c == "boss-matrix": return True, _matrix("boss matrix", args.manifest, args.out)
    if c == "random-battle-matrix": return True, _matrix("random battle matrix", args.manifest, args.out)
    if c == "text-matrix": return True, _matrix("text matrix", args.manifest, args.out)
    if c == "demo-certify": return True, demo_certify(args.manifest, args.out)
    if c == "studio": return True, studio(args.project, args.out)
    if c == "studio-build": return True, studio_build(args.project, args.out_dir, args.out)
    if c == "studio-report": return True, studio_report(args.project, args.out)
    if c == "dashboard-export": return True, dashboard_export(args.project, args.out)
    if c == "qa-board": return True, qa_board(args.project, args.out)
    if c == "visual-report": return True, visual_report(args.project, args.out)
    if c == "v30-new-project": return True, v30_new_project(args.project, args.name, args.system, args.goal, args.out)
    if c == "v30-import-source": return True, v30_import_source(args.project, args.source, args.kind, args.out)
    if c == "v30-build-sdk": return True, sdk_create(args.project, args.game, args.system, args.out)
    if c == "certify-release": return True, certify_release(args.root, args.out)
    if c == "v30-status": return True, v30_status(args.project, args.out)
    if c == "v30-capabilities": return True, v30_capabilities(args.out)
    if c == "v30-self-test": return True, v30_self_test(args.out)
    return False, None
