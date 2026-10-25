from __future__ import annotations

"""Dependency-free visual evidence primitives for ROMancer v7."""

import hashlib
from dataclasses import dataclass
from typing import Any

from .libretro_frontend import Frame


def _luma(r: int, g: int, b: int) -> int:
    # Integer BT.601-ish luma. Used only as a comparison metric, not colorimetry.
    return (77 * r + 150 * g + 29 * b) >> 8


def thumbnail_luma(frame: Frame, cols: int = 32, rows: int = 28) -> bytes:
    if cols <= 0 or rows <= 0:
        raise ValueError("thumbnail dimensions must be positive")
    out = bytearray(cols * rows)
    rgb = frame.rgb
    w, h = frame.width, frame.height
    for gy in range(rows):
        y0 = (gy * h) // rows
        y1 = max(y0 + 1, ((gy + 1) * h) // rows)
        for gx in range(cols):
            x0 = (gx * w) // cols
            x1 = max(x0 + 1, ((gx + 1) * w) // cols)
            total = count = 0
            # Small bounded sample grid to keep comparisons cheap on hires frames.
            sy = max(1, (y1 - y0) // 3)
            sx = max(1, (x1 - x0) // 3)
            for y in range(y0, y1, sy):
                for x in range(x0, x1, sx):
                    i = (y * w + x) * 3
                    total += _luma(rgb[i], rgb[i + 1], rgb[i + 2])
                    count += 1
            out[gy * cols + gx] = total // max(1, count)
    return bytes(out)


def frame_signature(frame: Frame, cols: int = 32, rows: int = 28) -> dict[str, Any]:
    thumb = thumbnail_luma(frame, cols, rows)
    return {
        "frame_index": frame.index,
        "width": frame.width,
        "height": frame.height,
        "pixel_format": frame.pixel_format,
        "rgb_sha256": frame.sha256(),
        "thumbnail": {"cols": cols, "rows": rows, "sha256": hashlib.sha256(thumb).hexdigest()},
        "mean_luma": round(sum(thumb) / len(thumb), 3) if thumb else 0.0,
        "black_cell_ratio": round(sum(1 for v in thumb if v <= 8) / len(thumb), 6) if thumb else 1.0,
    }


def compare_frames(a: Frame | None, b: Frame | None, cols: int = 32, rows: int = 28, threshold: int = 12) -> dict[str, Any]:
    if a is None or b is None:
        return {"comparable": False, "reason": "missing frame"}
    ta = thumbnail_luma(a, cols, rows)
    tb = thumbnail_luma(b, cols, rows)
    diffs = [abs(x - y) for x, y in zip(ta, tb)]
    changed = [d for d in diffs if d >= threshold]
    return {
        "comparable": True,
        "same_rgb_sha256": a.sha256() == b.sha256(),
        "mean_abs_luma_delta": round(sum(diffs) / max(1, len(diffs)), 4),
        "max_luma_delta": max(diffs) if diffs else 0,
        "changed_cell_ratio": round(len(changed) / max(1, len(diffs)), 6),
        "threshold": threshold,
        "grid": [cols, rows],
        "a": {"index": a.index, "size": [a.width, a.height], "sha256": a.sha256()},
        "b": {"index": b.index, "size": [b.width, b.height], "sha256": b.sha256()},
    }


def changed_bbox(a: Frame | None, b: Frame | None, cols: int = 64, rows: int = 56, threshold: int = 20) -> dict[str, Any]:
    """Approximate changed-region bounding box in normalized grid coordinates."""
    if a is None or b is None:
        return {"found": False, "reason": "missing frame"}
    ta = thumbnail_luma(a, cols, rows)
    tb = thumbnail_luma(b, cols, rows)
    pts = []
    for idx, (x, y) in enumerate(zip(ta, tb)):
        if abs(x - y) >= threshold:
            pts.append((idx % cols, idx // cols))
    if not pts:
        return {"found": False, "changed_cells": 0, "grid": [cols, rows]}
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return {
        "found": True,
        "changed_cells": len(pts),
        "grid": [cols, rows],
        "grid_bbox": [x0, y0, x1, y1],
        "normalized_bbox": [
            round(x0 / cols, 6), round(y0 / rows, 6),
            round((x1 + 1) / cols, 6), round((y1 + 1) / rows, 6),
        ],
    }


def freeze_report(frames: list[Frame], *, window: int = 120, tolerance: float = 0.15) -> dict[str, Any]:
    """Report whether the last N captured frames are visually static.

    This is intentionally a signal, not a claim of a CPU hang. A legitimate pause menu
    or static dialogue box can also be visually static, so callers must combine this with
    input and RAM evidence before calling a freeze.
    """
    if not frames:
        return {"enough_data": False, "reason": "no captured frames"}
    sample = frames[-max(2, window):]
    if len(sample) < 2:
        return {"enough_data": False, "captured": len(sample)}
    base = sample[0]
    deltas = []
    for fr in sample[1:]:
        c = compare_frames(base, fr, cols=16, rows=14, threshold=8)
        deltas.append(float(c.get("mean_abs_luma_delta", 0.0)))
    return {
        "enough_data": True,
        "captured": len(sample),
        "max_mean_delta": round(max(deltas) if deltas else 0.0, 4),
        "mean_delta": round(sum(deltas) / max(1, len(deltas)), 4),
        "visually_static": bool(deltas and max(deltas) <= tolerance),
        "tolerance": tolerance,
        "warning": "Visual staticness alone does not prove an emulator/CPU hang.",
    }
