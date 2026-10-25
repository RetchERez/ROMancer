from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from .rom_ident import identify_rom
from .util import write_json, read_json

PROJECT_DIRS = ["original", "work", "traces", "patches", "reports", "symbols", "notes", "evidence", "profiles", "playtests", "states", "frames", "memory", "runtime"]


def init_project(project: str | Path, rom: str | Path, copy_rom: bool = True) -> dict:
    root = Path(project)
    root.mkdir(parents=True, exist_ok=True)
    for d in PROJECT_DIRS:
        (root / d).mkdir(exist_ok=True)
    rom_path = Path(rom)
    target = root / "original" / rom_path.name
    if copy_rom:
        shutil.copy2(rom_path, target)
        id_path = target
    else:
        id_path = rom_path
    ident = identify_rom(id_path)
    meta = {
        "name": root.name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "rom_original": str(target if copy_rom else rom_path),
        "identity": ident,
        "romancer_version": "7.0.0",
    }
    write_json(root / "project.json", meta)
    write_json(root / "reports" / "identify.json", ident)
    return meta


def load_project(project: str | Path) -> dict:
    return read_json(Path(project) / "project.json")


def project_report(project: str | Path) -> str:
    root = Path(project)
    meta = load_project(root)
    ident = meta.get("identity", {})
    lines = []
    lines.append("ROMancer Project Report")
    lines.append("=======================")
    lines.append("")
    lines.append(f"Project: {meta.get('name')}")
    lines.append(f"Created UTC: {meta.get('created_utc')}")
    lines.append(f"ROM: {meta.get('rom_original')}")
    lines.append(f"System: {ident.get('system')}")
    lines.append(f"Size: {ident.get('size_bytes')} bytes")
    lines.append(f"SHA1: {ident.get('sha1')}")
    lines.append(f"CRC32: {ident.get('crc32')}")
    if ident.get("mapping_guess"):
        lines.append(f"SNES mapping guess: {ident.get('mapping_guess')}")
    if ident.get("mapper") is not None:
        lines.append(f"NES mapper: {ident.get('mapper')}")
    if ident.get("domestic_title"):
        lines.append(f"Genesis domestic title: {ident.get('domestic_title')}")
    lines.append("")
    lines.append("Notes:")
    for n in ident.get("notes", []):
        lines.append(f"- {n}")
    text = "\n".join(lines) + "\n"
    out = root / "reports" / "project_report.txt"
    out.write_text(text, encoding="utf-8")
    return text
