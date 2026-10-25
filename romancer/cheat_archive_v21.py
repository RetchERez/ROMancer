from __future__ import annotations

"""ROMancer v21 source-grounded cheat-code archive builder.

This module normalizes cheat-code records from public or user-supplied source
folders. It does not bundle ROMs, BIOS files, emulator cores, save states, or
commercial game assets.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .util import write_json

LIBRETRO_REPO = "https://github.com/libretro/libretro-database.git"
V21_VERSION = "21.0.0"

CHEAT_SCHEMA_FIELDS = [
    "record_id",
    "source_priority",
    "platform",
    "platform_family",
    "game_title",
    "game_region",
    "game_revision",
    "media_identifier",
    "rom_crc",
    "rom_md5",
    "rom_sha1",
    "disc_serial",
    "device_or_format",
    "code_type",
    "code_text",
    "effect_name",
    "effect_detail",
    "activation_notes",
    "master_code_required",
    "requires_boot_code",
    "requires_specific_emulator",
    "known_conflicts",
    "verified_status",
    "verification_method",
    "original_author",
    "source_name",
    "source_url",
    "source_license",
    "source_file_path",
    "source_last_checked",
    "parse_confidence",
    "notes",
]

SAFE_STATUS_LABELS = [
    "verified",
    "fixed",
    "not reachable",
    "not inspected",
    "release candidate",
    "final",
]

SOURCE_INVENTORY = [
    {
        "source_name": "libretro/libretro-database",
        "use": "RetroArch .cht files and broad cross-platform emulator cheat coverage",
        "accepted_inputs": ["local clone", "existing source folder", "optional git clone"],
        "license_note": "CC BY-SA 4.0 per repository license, preserve attribution and share-alike terms",
        "limitations": [
            "Original cheat-device provenance is not always preserved in .cht files",
            "Runtime gameplay validation is outside parser scope",
        ],
    },
    {
        "source_name": "GameHacking.org exports",
        "use": "Device-labeled Game Genie, Pro Action Replay, Action Replay, GameShark, CodeBreaker, Xploder, Xplorer, and raw codes when exported by the user",
        "accepted_inputs": ["CSV", "TSV", "JSON", "JSONL"],
        "license_note": "User must verify redistribution rights for any exported data before publishing",
        "limitations": [
            "Complete offline coverage requires an authorized export or local source dump",
            "Column mapping must be checked before final release",
        ],
    },
    {
        "source_name": "MAME cheat XML ecosystem",
        "use": "Arcade emulator cheat definitions and emulator-side game enhancement records",
        "accepted_inputs": ["future XML adapter", "generic exports"],
        "license_note": "Use only files with clear redistribution terms",
        "limitations": ["MAME XML records are emulator definitions, not retail cheat-device codes"],
    },
    {
        "source_name": "Gecko/Ocarina and CWCheat archives",
        "use": "GameCube, Wii, and PSP cheat ecosystems when supplied as local exports",
        "accepted_inputs": ["future INI/DB adapters", "generic exports"],
        "license_note": "Use only files with clear redistribution terms",
        "limitations": ["Parser support is conservative unless data is supplied in generic CSV/TSV/JSON form"],
    },
]

DEVICE_FAMILIES = [
    "Game Genie",
    "Pro Action Replay",
    "Action Replay",
    "GameShark",
    "GameShark Pro",
    "GameShark CDX",
    "CodeBreaker",
    "Xploder / Xplorer",
    "Gecko",
    "Ocarina",
    "CWCheat",
    "MAME cheat XML",
    "RetroArch .cht",
    "Emulator raw RAM/write codes",
]

FORBIDDEN_SUFFIXES = {
    ".srm", ".sav", ".state", ".smc", ".sfc", ".nes", ".gba", ".gb", ".gbc", ".gen", ".md",
    ".iso", ".cue", ".bin", ".chd", ".ccd", ".img", ".sub", ".n64", ".z64", ".v64",
}


@dataclass
class CheatRecord:
    record_id: str
    source_priority: str
    platform: str
    platform_family: str
    game_title: str
    game_region: str
    game_revision: str
    media_identifier: str
    rom_crc: str
    rom_md5: str
    rom_sha1: str
    disc_serial: str
    device_or_format: str
    code_type: str
    code_text: str
    effect_name: str
    effect_detail: str
    activation_notes: str
    master_code_required: str
    requires_boot_code: str
    requires_specific_emulator: str
    known_conflicts: str
    verified_status: str
    verification_method: str
    original_author: str
    source_name: str
    source_url: str
    source_license: str
    source_file_path: str
    source_last_checked: str
    parse_confidence: str
    notes: str


def stable_id(parts: Iterable[str]) -> str:
    raw = "\x1f".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:24]


def normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def strip_outer_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def infer_region_from_title(title: str) -> str:
    tags = re.findall(r"\(([^()]+)\)", title or "")
    out: list[str] = []
    for tag in tags:
        t = tag.lower()
        if any(k in t for k in [
            "usa", "europe", "japan", "world", "australia", "korea", "brazil", "germany",
            "france", "spain", "italy", "sweden", "china", "asia", "ntsc", "pal",
        ]):
            out.append(tag)
    return "; ".join(out) if out else "unknown"


def infer_revision_from_title(title: str) -> str:
    tags = re.findall(r"\(([^()]+)\)", title or "")
    out: list[str] = []
    for tag in tags:
        t = tag.lower()
        if any(k in t for k in ["rev", "version", "v1.", "v2.", "proto", "beta", "sample"]):
            out.append(tag)
    return "; ".join(out) if out else "unknown"


def platform_family(platform: str) -> str:
    p = (platform or "").lower()
    if "nintendo" in p or "nes" in p or "game boy" in p or "gamecube" in p or "wii" in p:
        return "Nintendo"
    if "sega" in p or "genesis" in p or "mega drive" in p or "saturn" in p or "dreamcast" in p:
        return "Sega"
    if "sony" in p or "playstation" in p or "psp" in p:
        return "Sony"
    if "mame" in p or "arcade" in p or "fbneo" in p:
        return "Arcade"
    if "atari" in p:
        return "Atari"
    if "nec" in p or "pc engine" in p or "turbografx" in p:
        return "NEC"
    return "Other"


HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
GG_HYPHEN_RE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b")
NES_GG_RE = re.compile(r"\b[APZLGITYEOXUKSVN]{6}([APZLGITYEOXUKSVN]{2})?\b")


def infer_device_or_format(code: str, desc: str, source_path: str) -> tuple[str, str, str]:
    text = " ".join([code or "", desc or "", source_path or ""]).lower()
    explicit = [
        ("game shark pro", "GameShark Pro"),
        ("gameshark pro", "GameShark Pro"),
        ("gameshark cdx", "GameShark CDX"),
        ("game shark cdx", "GameShark CDX"),
        ("pro action replay", "Pro Action Replay"),
        ("action replay", "Action Replay"),
        ("gameshark", "GameShark"),
        ("game shark", "GameShark"),
        ("codebreaker", "CodeBreaker"),
        ("code breaker", "CodeBreaker"),
        ("xploder", "Xploder"),
        ("xplorer", "Xplorer"),
        ("game genie", "Game Genie"),
        ("gecko", "Gecko"),
        ("ocarina", "Ocarina"),
        ("cwcheat", "CWCheat"),
        ("mame cheat", "MAME cheat XML"),
    ]
    for needle, label in explicit:
        if needle in text:
            return label, "explicit_source_text", "high"
    if re.search(r"\bpar\b", text):
        return "Pro Action Replay", "explicit_source_text", "high"
    up = (code or "").upper()
    if NES_GG_RE.search(up):
        return "Game Genie-like", "nes_game_genie_pattern", "medium"
    if GG_HYPHEN_RE.search(up):
        return "Game Genie-like", "hyphenated_game_genie_pattern", "medium"
    compact = up.replace(" ", "").replace("+", "").replace("\n", "").replace(":", "")
    if compact and HEX_RE.match(compact):
        return "RetroArch .cht / raw or core-specific", "generic_hex_or_raw_pattern", "low"
    return "RetroArch .cht / unknown original device", "not_inferred", "low"


def _make_record(**kwargs: str) -> CheatRecord:
    defaults = {field: "" for field in CHEAT_SCHEMA_FIELDS}
    defaults.update({
        "source_priority": "primary",
        "game_region": "unknown",
        "game_revision": "unknown",
        "media_identifier": "unknown",
        "rom_crc": "unknown",
        "rom_md5": "unknown",
        "rom_sha1": "unknown",
        "disc_serial": "unknown",
        "effect_name": "unknown",
        "master_code_required": "unknown",
        "requires_boot_code": "unknown",
        "requires_specific_emulator": "unknown",
        "known_conflicts": "unknown",
        "verified_status": "not inspected",
        "verification_method": "parsed from source file only",
        "original_author": "unknown",
        "source_license": "unknown",
        "source_last_checked": "local run",
        "parse_confidence": "low",
    })
    defaults.update(kwargs)
    return CheatRecord(**{field: str(defaults.get(field, "")) for field in CHEAT_SCHEMA_FIELDS})


def parse_retroarch_cht(path: str | Path, root: str | Path, source_last_checked: str = "local run") -> list[CheatRecord]:
    path = Path(path)
    root = Path(root)
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    parts = rel.parts
    try:
        cht_index = parts.index("cht")
        platform = parts[cht_index + 1]
    except Exception:
        platform = parts[0] if len(parts) > 1 else "unknown"
    game_title = path.stem
    entries: dict[int, dict[str, str]] = {}
    text = path.read_text("utf-8", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        m = re.match(r"cheat(\d+)_(.+)", k.strip())
        if not m:
            continue
        idx = int(m.group(1))
        field = m.group(2)
        entries.setdefault(idx, {})[field] = strip_outer_quotes(v.strip())
    records: list[CheatRecord] = []
    for idx in sorted(entries):
        item = entries[idx]
        code = normalize_ws(item.get("code", ""))
        desc = normalize_ws(item.get("desc", item.get("description", "")))
        if not code and not desc:
            continue
        device, code_type, confidence = infer_device_or_format(code, desc, str(rel))
        records.append(_make_record(
            record_id=stable_id(["libretro", str(rel), str(idx), code, desc]),
            platform=platform,
            platform_family=platform_family(platform),
            game_title=game_title,
            game_region=infer_region_from_title(game_title),
            game_revision=infer_revision_from_title(game_title),
            device_or_format=device,
            code_type=code_type,
            code_text=code,
            effect_name=desc or "unknown",
            activation_notes=f"RetroArch index cheat{idx}; enable value={item.get('enable', 'not specified')}",
            requires_specific_emulator="RetroArch/libretro core support may be required",
            source_name="libretro/libretro-database",
            source_url=LIBRETRO_REPO,
            source_license="CC BY-SA 4.0 per repository license",
            source_file_path=str(rel).replace(os.sep, "/"),
            source_last_checked=source_last_checked,
            parse_confidence=confidence,
            notes="Original cheat-device provenance is not guaranteed by .cht format unless explicit in source text",
        ))
    return records


def parse_generic_csv_tsv(path: str | Path, source_last_checked: str = "local run") -> list[CheatRecord]:
    path = Path(path)
    sample = path.read_text("utf-8", errors="replace")[:4096]
    dialect = csv.excel_tab if sample.count("\t") > sample.count(",") else csv.excel
    records: list[CheatRecord] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        for row_num, row in enumerate(reader, 1):
            lower = {str(k).lower().strip(): (v or "") for k, v in row.items()}
            code = normalize_ws(lower.get("code") or lower.get("codes") or lower.get("cheat") or lower.get("code_text") or "")
            desc = normalize_ws(lower.get("name") or lower.get("description") or lower.get("effect") or lower.get("title") or "")
            game = normalize_ws(lower.get("game") or lower.get("game_title") or lower.get("title") or path.stem)
            platform = normalize_ws(lower.get("system") or lower.get("platform") or lower.get("console") or "unknown")
            device = normalize_ws(lower.get("device") or lower.get("format") or lower.get("code_format") or "")
            if not code and not desc:
                continue
            inferred_device, code_type, confidence = infer_device_or_format(code, desc, str(path))
            if device:
                inferred_device = device
                confidence = "high"
            records.append(_make_record(
                record_id=stable_id(["generic", str(path), str(row_num), code, desc]),
                platform=platform,
                platform_family=platform_family(platform),
                game_title=game,
                game_region=lower.get("region") or infer_region_from_title(game),
                game_revision=lower.get("revision") or infer_revision_from_title(game),
                media_identifier=lower.get("identifier") or lower.get("serial") or lower.get("crc") or "unknown",
                rom_crc=lower.get("rom_crc") or lower.get("crc") or "unknown",
                rom_md5=lower.get("rom_md5") or lower.get("md5") or "unknown",
                rom_sha1=lower.get("rom_sha1") or lower.get("sha1") or "unknown",
                disc_serial=lower.get("disc_serial") or lower.get("serial") or "unknown",
                device_or_format=inferred_device,
                code_type=lower.get("code_type") or code_type,
                code_text=code,
                effect_name=desc or "unknown",
                effect_detail=lower.get("notes") or lower.get("effect_detail") or "",
                activation_notes=lower.get("activation_notes") or "",
                master_code_required=lower.get("master_code_required") or "unknown",
                requires_boot_code=lower.get("requires_boot_code") or "unknown",
                requires_specific_emulator=lower.get("requires_specific_emulator") or "unknown",
                known_conflicts=lower.get("known_conflicts") or "unknown",
                verification_method="parsed from source export only",
                original_author=lower.get("author") or lower.get("hacker") or "unknown",
                source_name=lower.get("source") or "local generic export",
                source_url=lower.get("source_url") or "",
                source_license=lower.get("license") or "unknown",
                source_file_path=str(path),
                source_last_checked=source_last_checked,
                parse_confidence=confidence,
                notes="Generic export parser; verify column mapping before final release",
            ))
    return records


def _rows_from_json_obj(obj: Any) -> list[Any]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ["codes", "cheats", "results", "data"]:
            if isinstance(obj.get(key), list):
                return obj[key]
        return [obj]
    return []


def parse_generic_json(path: str | Path, source_last_checked: str = "local run") -> list[CheatRecord]:
    path = Path(path)
    text = path.read_text("utf-8", errors="replace").strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        rows: list[Any] = []
        for line_num, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                sys.stderr.write(f"[WARN] JSONL parse fail {path}:{line_num}: {exc}\n")
    else:
        rows = _rows_from_json_obj(json.loads(text))
    records: list[CheatRecord] = []
    for idx, obj in enumerate(rows):
        if not isinstance(obj, dict):
            continue
        lower = {str(k).lower().strip(): v for k, v in obj.items()}
        def s(key: str, default: str = "") -> str:
            return str(lower.get(key, default) or default)
        code = normalize_ws(s("code") or s("codes") or s("cheat") or s("code_text"))
        desc = normalize_ws(s("name") or s("description") or s("effect") or s("title"))
        game = normalize_ws(s("game") or s("game_title") or path.stem)
        platform = normalize_ws(s("system") or s("platform") or s("console") or "unknown")
        device = normalize_ws(s("device") or s("format") or s("code_format"))
        if not code and not desc:
            continue
        inferred_device, code_type, confidence = infer_device_or_format(code, desc, str(path))
        if device:
            inferred_device = device
            confidence = "high"
        records.append(_make_record(
            record_id=stable_id(["json", str(path), str(idx), code, desc]),
            platform=platform,
            platform_family=platform_family(platform),
            game_title=game,
            game_region=s("region") or infer_region_from_title(game),
            game_revision=s("revision") or infer_revision_from_title(game),
            media_identifier=s("identifier") or s("serial") or s("crc") or "unknown",
            rom_crc=s("rom_crc") or s("crc") or "unknown",
            rom_md5=s("rom_md5") or s("md5") or "unknown",
            rom_sha1=s("rom_sha1") or s("sha1") or "unknown",
            disc_serial=s("disc_serial") or s("serial") or "unknown",
            device_or_format=inferred_device,
            code_type=s("code_type") or code_type,
            code_text=code,
            effect_name=desc or "unknown",
            effect_detail=s("notes") or s("effect_detail"),
            activation_notes=s("activation_notes"),
            master_code_required=s("master_code_required") or "unknown",
            requires_boot_code=s("requires_boot_code") or "unknown",
            requires_specific_emulator=s("requires_specific_emulator") or "unknown",
            known_conflicts=s("known_conflicts") or "unknown",
            verification_method="parsed from source export only",
            original_author=s("author") or s("hacker") or "unknown",
            source_name=s("source") or "local generic JSON export",
            source_url=s("source_url"),
            source_license=s("license") or "unknown",
            source_file_path=str(path),
            source_last_checked=source_last_checked,
            parse_confidence=confidence,
            notes="Generic JSON parser; verify field mapping before final release",
        ))
    return records


def clone_or_update_libretro(workdir: str | Path) -> tuple[Path | None, list[str]]:
    warnings: list[str] = []
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    dst = workdir / "libretro-database"
    try:
        if dst.exists():
            subprocess.check_call(["git", "-C", str(dst), "pull", "--ff-only"])
        else:
            subprocess.check_call(["git", "clone", "--depth", "1", LIBRETRO_REPO, str(dst)])
        return dst, warnings
    except Exception as exc:
        warnings.append(f"Could not clone or update libretro database: {exc}")
        return None, warnings


def collect_records(
    libretro_dir: str | None = None,
    extra_dirs: list[str] | None = None,
    clone_libretro: bool = False,
    workdir: str = "sources",
    source_last_checked: str = "local run",
) -> tuple[list[CheatRecord], list[str]]:
    warnings: list[str] = []
    roots: list[Path] = []
    if clone_libretro:
        repo, clone_warnings = clone_or_update_libretro(workdir)
        warnings.extend(clone_warnings)
        if repo is not None:
            roots.append(repo)
    if libretro_dir:
        roots.append(Path(libretro_dir))
    records: list[CheatRecord] = []
    for root in roots:
        cht_root = root / "cht"
        if not cht_root.exists():
            warnings.append(f"No cht folder found under {root}")
            continue
        for path in sorted(cht_root.rglob("*.cht")):
            try:
                records.extend(parse_retroarch_cht(path, root, source_last_checked))
            except Exception as exc:
                warnings.append(f"Failed parsing {path}: {exc}")
    for extra in extra_dirs or []:
        extra_path = Path(extra)
        if not extra_path.exists():
            warnings.append(f"Extra source dir not found: {extra_path}")
            continue
        for path in sorted(extra_path.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            try:
                if suffix in [".csv", ".tsv"]:
                    records.extend(parse_generic_csv_tsv(path, source_last_checked))
                elif suffix in [".json", ".jsonl"]:
                    records.extend(parse_generic_json(path, source_last_checked))
                elif suffix == ".cht":
                    records.extend(parse_retroarch_cht(path, extra_path, source_last_checked))
            except Exception as exc:
                warnings.append(f"Failed parsing {path}: {exc}")
    return records, warnings


def dedupe_records(records: list[CheatRecord]) -> list[CheatRecord]:
    seen: set[tuple[str, str, str, str, str, str, str, str]] = set()
    out: list[CheatRecord] = []
    for r in records:
        key = (
            r.platform,
            r.game_title,
            r.game_region,
            r.game_revision,
            r.device_or_format,
            r.code_text,
            r.effect_name,
            r.source_name,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def record_to_dict(r: CheatRecord) -> dict[str, Any]:
    return asdict(r)


def write_txt(records: list[CheatRecord], path: str | Path, warnings: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("MASTER GAME CHEAT CODES\n")
        f.write("Source-grounded ROMancer v21 archive\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total records: {len(records)}\n")
        f.write("Verification status: parsed source records, not gameplay-tested unless a source field says otherwise\n")
        f.write("Policy: no ROMs, BIOS files, emulator cores, save states, or commercial game assets are included\n\n")
        if warnings:
            f.write("WARNINGS\n")
            for w in warnings:
                f.write(f"* {w}\n")
            f.write("\n")
        current_platform = None
        current_game = None
        for r in sorted(records, key=lambda x: (x.platform, x.game_title, x.device_or_format, x.effect_name, x.code_text)):
            if r.platform != current_platform:
                current_platform = r.platform
                current_game = None
                f.write("\n" + "#" * 80 + "\n")
                f.write(f"PLATFORM: {r.platform}\n")
                f.write("#" * 80 + "\n")
            if r.game_title != current_game:
                current_game = r.game_title
                f.write("\n" + "-" * 80 + "\n")
                f.write(f"GAME: {r.game_title}\n")
                f.write(f"REGION: {r.game_region}\n")
                f.write(f"REVISION: {r.game_revision}\n")
                f.write("-" * 80 + "\n")
            f.write(f"RECORD_ID: {r.record_id}\n")
            f.write(f"DEVICE_OR_FORMAT: {r.device_or_format}\n")
            f.write(f"CODE_TYPE: {r.code_type}\n")
            f.write("CODE:\n")
            for line in (r.code_text or "").splitlines() or [""]:
                f.write(f"  {line}\n")
            f.write(f"EFFECT: {r.effect_name}\n")
            if r.effect_detail:
                f.write(f"EFFECT_DETAIL: {r.effect_detail}\n")
            f.write(f"ACTIVATION_NOTES: {r.activation_notes}\n")
            f.write(f"MASTER_CODE_REQUIRED: {r.master_code_required}\n")
            f.write(f"REQUIRES_BOOT_CODE: {r.requires_boot_code}\n")
            f.write(f"REQUIRES_SPECIFIC_EMULATOR: {r.requires_specific_emulator}\n")
            f.write(f"KNOWN_CONFLICTS: {r.known_conflicts}\n")
            f.write(f"VERIFIED_STATUS: {r.verified_status}\n")
            f.write(f"VERIFICATION_METHOD: {r.verification_method}\n")
            f.write(f"AUTHOR: {r.original_author}\n")
            f.write(f"SOURCE: {r.source_name}\n")
            f.write(f"SOURCE_URL: {r.source_url}\n")
            f.write(f"SOURCE_LICENSE: {r.source_license}\n")
            f.write(f"SOURCE_FILE: {r.source_file_path}\n")
            f.write(f"PARSE_CONFIDENCE: {r.parse_confidence}\n")
            if r.notes:
                f.write(f"NOTES: {r.notes}\n")
            f.write("\n")


def write_tsv(records: list[CheatRecord], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = CHEAT_SCHEMA_FIELDS
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for r in records:
            writer.writerow(record_to_dict(r))


def write_jsonl(records: list[CheatRecord], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(record_to_dict(r), ensure_ascii=False, sort_keys=True) + "\n")


def build_counts(records: list[CheatRecord]) -> dict[str, dict[str, int]]:
    by_platform: dict[str, int] = {}
    by_device: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in records:
        by_platform[r.platform] = by_platform.get(r.platform, 0) + 1
        by_device[r.device_or_format] = by_device.get(r.device_or_format, 0) + 1
        by_status[r.verified_status] = by_status.get(r.verified_status, 0) + 1
    return {"platform": by_platform, "device_or_format": by_device, "verified_status": by_status}


def write_report(records: list[CheatRecord], path: str | Path, warnings: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = build_counts(records)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("ROMANCER V21 CHEAT ARCHIVE BUILD REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total records: {len(records)}\n")
        f.write(f"Warnings: {len(warnings)}\n\n")
        if warnings:
            f.write("WARNINGS\n")
            for w in warnings:
                f.write(f"* {w}\n")
            f.write("\n")
        f.write("COUNTS BY DEVICE_OR_FORMAT\n")
        for k, v in sorted(counts["device_or_format"].items(), key=lambda kv: (-kv[1], kv[0])):
            f.write(f"{k}\t{v}\n")
        f.write("\nCOUNTS BY PLATFORM\n")
        for k, v in sorted(counts["platform"].items(), key=lambda kv: (-kv[1], kv[0])):
            f.write(f"{k}\t{v}\n")
        f.write("\nCOUNTS BY VERIFIED_STATUS\n")
        for k, v in sorted(counts["verified_status"].items(), key=lambda kv: (-kv[1], kv[0])):
            f.write(f"{k}\t{v}\n")


def cheat_schema(out: str | None = None) -> dict[str, Any]:
    result = {
        "tool": "ROMancer",
        "version": V21_VERSION,
        "feature": "v21 cheat-code archive schema",
        "fields": CHEAT_SCHEMA_FIELDS,
        "status_labels": SAFE_STATUS_LABELS,
        "device_families": DEVICE_FAMILIES,
        "policy": "Codes are source records. Runtime game behavior is not assumed without separate emulator or hardware proof.",
    }
    if out:
        write_json(out, result)
    return result


def cheat_sources(out: str | None = None) -> dict[str, Any]:
    result = {
        "tool": "ROMancer",
        "version": V21_VERSION,
        "feature": "v21 cheat-code source inventory",
        "sources": SOURCE_INVENTORY,
        "do_not_include": [
            "ROMs",
            "BIOS files",
            "emulator cores",
            "save states",
            "commercial manuals unless explicitly licensed for redistribution",
            "online multiplayer cheating material",
            "DRM circumvention or piracy material",
        ],
    }
    if out:
        write_json(out, result)
    return result


def audit_source_dir(root: str, out: str | None = None) -> dict[str, Any]:
    rootp = Path(root)
    files: list[Path] = []
    if rootp.exists():
        files = [p for p in rootp.rglob("*") if p.is_file()]
    counts: dict[str, int] = {}
    forbidden: list[str] = []
    for p in files:
        suffix = p.suffix.lower()
        counts[suffix or "[no suffix]"] = counts.get(suffix or "[no suffix]", 0) + 1
        if suffix in FORBIDDEN_SUFFIXES:
            forbidden.append(str(p.relative_to(rootp)))
    accepted = sum(counts.get(s, 0) for s in [".cht", ".csv", ".tsv", ".json", ".jsonl"])
    result = {
        "tool": "ROMancer",
        "version": V21_VERSION,
        "feature": "v21 cheat source audit",
        "root": str(rootp),
        "exists": rootp.exists(),
        "file_count": len(files),
        "accepted_source_file_count": accepted,
        "suffix_counts": counts,
        "forbidden_payload_candidates": forbidden[:200],
        "ok_for_source_archive": rootp.exists() and not forbidden,
        "policy": "Forbidden candidates are not deleted by audit. Remove them before publishing a package.",
    }
    if out:
        write_json(out, result)
    return result


def build_cheat_archive(
    out: str = "MASTER_GAME_CHEAT_CODES.txt",
    libretro_dir: str | None = None,
    extra_dirs: list[str] | None = None,
    clone_libretro: bool = False,
    workdir: str = "sources",
    source_last_checked: str = "local run",
) -> dict[str, Any]:
    records, warnings = collect_records(
        libretro_dir=libretro_dir,
        extra_dirs=extra_dirs or [],
        clone_libretro=clone_libretro,
        workdir=workdir,
        source_last_checked=source_last_checked,
    )
    records = dedupe_records(records)
    out_txt = Path(out)
    out_tsv = out_txt.with_suffix(".tsv")
    out_jsonl = out_txt.with_suffix(".jsonl")
    out_report = out_txt.with_name(out_txt.stem + "_BUILD_REPORT.txt")
    write_txt(records, out_txt, warnings)
    write_tsv(records, out_tsv)
    write_jsonl(records, out_jsonl)
    write_report(records, out_report, warnings)
    result = {
        "tool": "ROMancer",
        "version": V21_VERSION,
        "feature": "v21 cheat-code archive build",
        "record_count": len(records),
        "unique_record_count": len(records),
        "outputs": {
            "txt": str(out_txt),
            "tsv": str(out_tsv),
            "jsonl": str(out_jsonl),
            "report": str(out_report),
        },
        "warnings": warnings,
        "counts": build_counts(records),
        "status": "release candidate" if records and not warnings else "not inspected",
        "policy": "Generated files contain cheat-code records only. They do not contain ROMs, BIOS files, emulator cores, save states, or commercial assets.",
    }
    return result


def v21_self_test(out: str | None = None) -> dict[str, Any]:
    import tempfile
    tests: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="romancer_v21_") as td0:
        td = Path(td0)
        cht = td / "libretro-database" / "cht" / "Nintendo - Nintendo Entertainment System"
        cht.mkdir(parents=True)
        sample = cht / "Fixture Game (USA).cht"
        sample.write_text(
            "cheats = 2\n"
            "cheat0_desc = \"Game Genie Infinite Lives\"\n"
            "cheat0_code = \"SXIOPO\"\n"
            "cheat0_enable = false\n"
            "cheat1_desc = \"Pro Action Replay Max Gold\"\n"
            "cheat1_code = \"7E1234FF\"\n"
            "cheat1_enable = false\n",
            encoding="utf-8",
        )
        extra = td / "extra"
        extra.mkdir()
        (extra / "export.csv").write_text(
            "platform,game,device,code,effect,region\n"
            "Super Nintendo,Fixture RPG,Action Replay,7E0001FF,Max HP,USA\n",
            encoding="utf-8",
        )
        parsed = parse_retroarch_cht(sample, td / "libretro-database")
        tests.append({"name": "parse RetroArch cht records", "ok": len(parsed) == 2})
        tests.append({"name": "detect explicit Pro Action Replay text", "ok": any(r.device_or_format == "Pro Action Replay" for r in parsed)})
        schema = cheat_schema()
        tests.append({"name": "schema includes provenance fields", "ok": "source_file_path" in schema["fields"] and "verified_status" in schema["fields"]})
        audit = audit_source_dir(str(td / "libretro-database"))
        tests.append({"name": "source audit accepts cht folder", "ok": audit["accepted_source_file_count"] == 1 and audit["ok_for_source_archive"]})
        build = build_cheat_archive(
            out=str(td / "MASTER_GAME_CHEAT_CODES.txt"),
            libretro_dir=str(td / "libretro-database"),
            extra_dirs=[str(extra)],
        )
        tests.append({"name": "build writes txt tsv jsonl report", "ok": all(Path(p).exists() for p in build["outputs"].values())})
        tests.append({"name": "build dedupes and counts three records", "ok": build["record_count"] == 3})
        no_payload = audit_source_dir(str(extra))
        tests.append({"name": "extra export audit has no forbidden payload", "ok": not no_payload["forbidden_payload_candidates"]})
    result = {
        "tool": "ROMancer",
        "version": V21_VERSION,
        "feature": "v21 cheat archive self-test",
        "ok": all(bool(t.get("ok")) for t in tests),
        "tests": tests,
    }
    if out:
        write_json(out, result)
    return result
