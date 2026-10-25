from __future__ import annotations

"""RAM candidate discovery from controlled observations.

The functions in this module deliberately report offsets within the memory buffer exposed
by a libretro core. They do not invent CPU bus addresses. A game/system profile may add a
verified mapping from exposed-buffer offset to CPU address later.
"""

import json
from pathlib import Path
from typing import Any


def find_value(data: bytes, value: int, *, widths: list[int] | None = None, endian: str = "both", signed: bool = False, alignment: int = 1, limit: int = 5000) -> dict[str, Any]:
    widths = widths or [1, 2, 3, 4]
    matches = []
    for width in widths:
        if width <= 0:
            continue
        endians = ["little", "big"] if endian == "both" and width > 1 else ([endian] if endian in {"little", "big"} else ["little"])
        for byteorder in endians:
            try:
                needle = int(value).to_bytes(width, byteorder=byteorder, signed=signed)
            except OverflowError:
                continue
            start = 0
            while len(matches) < limit:
                pos = data.find(needle, start)
                if pos < 0:
                    break
                if alignment <= 1 or pos % alignment == 0:
                    matches.append({"offset": pos, "offset_hex": f"0x{pos:X}", "width": width, "endian": byteorder, "signed": signed})
                start = pos + 1
    return {"value": value, "buffer_size": len(data), "match_count": len(matches), "matches": matches, "truncated": len(matches) >= limit}


def changed_offsets(a: bytes, b: bytes, *, limit: int = 10000) -> dict[str, Any]:
    n = min(len(a), len(b))
    offsets = [i for i in range(n) if a[i] != b[i]]
    if len(a) != len(b):
        offsets.extend(range(n, max(len(a), len(b))))
    return {
        "before_size": len(a), "after_size": len(b), "changed_count": len(offsets),
        "offsets": offsets[:limit], "truncated": len(offsets) > limit,
    }


def correlate_numeric_series(observations: list[tuple[int, bytes]], *, widths: list[int] | None = None, endian: str = "both", signed: bool = False, alignment: int = 1, max_candidates: int = 5000) -> dict[str, Any]:
    """Find offsets whose encoded memory value equals every supplied observed value."""
    if len(observations) < 2:
        raise ValueError("At least two value+snapshot observations are required")
    widths = widths or [1, 2, 3, 4]
    first_value, first_data = observations[0]
    initial = find_value(first_data, first_value, widths=widths, endian=endian, signed=signed, alignment=alignment, limit=max_candidates)
    candidates = initial["matches"]
    survivors = []
    for cand in candidates:
        off = int(cand["offset"]); width = int(cand["width"]); byteorder = cand["endian"]
        good = True
        actual_values = []
        for expected, data in observations:
            if off + width > len(data):
                good = False; break
            actual = int.from_bytes(data[off:off + width], byteorder=byteorder, signed=signed)
            actual_values.append(actual)
            if actual != expected:
                good = False; break
        if good:
            survivors.append({**cand, "observed_values": actual_values})
    return {
        "observation_count": len(observations),
        "observed_values": [v for v, _ in observations],
        "initial_candidate_count": len(candidates),
        "survivor_count": len(survivors),
        "candidates": survivors,
        "interpretation": "Offsets are relative to the libretro-exposed memory region. CPU bus address is unknown unless independently mapped.",
    }


def rank_monotonic_candidates(snapshots: list[bytes], direction: str = "changed", max_results: int = 200) -> dict[str, Any]:
    """Rank byte offsets by how consistently they change between sequential snapshots."""
    if len(snapshots) < 2:
        raise ValueError("At least two snapshots are required")
    n = min(len(s) for s in snapshots)
    scores = []
    for off in range(n):
        vals = [s[off] for s in snapshots]
        transitions = sum(1 for a, b in zip(vals, vals[1:]) if a != b)
        inc = sum(1 for a, b in zip(vals, vals[1:]) if b > a)
        dec = sum(1 for a, b in zip(vals, vals[1:]) if b < a)
        if direction == "increase": score = inc
        elif direction == "decrease": score = dec
        else: score = transitions
        if score:
            scores.append({"offset": off, "offset_hex": f"0x{off:X}", "score": score, "transitions": transitions, "increases": inc, "decreases": dec, "values": vals})
    scores.sort(key=lambda x: (x["score"], x["transitions"]), reverse=True)
    return {"snapshot_count": len(snapshots), "bytes_compared": n, "direction": direction, "candidates": scores[:max_results]}


def parse_observation_specs(specs: list[str]) -> list[tuple[int, bytes]]:
    observations = []
    for spec in specs:
        if "=" not in spec:
            raise ValueError("Observation must be VALUE=SNAPSHOT_FILE")
        value_text, path = spec.split("=", 1)
        value = int(value_text, 0)
        observations.append((value, Path(path).read_bytes()))
    return observations
