"""Parse an eMouseAtlas ITK-SnAP anatomy label file.

The file maps a voxel index value in the *_anatomy.nii volume to an anatomical
component: index, RGB colour, EMAPA ontology id and a human-readable name.

Example line (whitespace separated, label quoted):
      16    0    0  128 1.0      1 1 "EMAPA:18601 aorta"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_LABEL_RE = re.compile(r'EMAPA:?(\d+)\s+(.*)')


@dataclass(frozen=True)
class Label:
    index: int          # voxel value in the anatomy volume
    rgb: tuple[int, int, int]
    emapa: str          # e.g. "EMAPA:18601"  (stable organ id across stages)
    name: str           # e.g. "aorta"


def parse_labels(path: str | Path) -> dict[int, Label]:
    """Return {index: Label} for every real component (skips index 0 / Clear Label)."""
    labels: dict[int, Label] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # IDX R G B A VIS MSH "LABEL"
        m = re.match(r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+"(.*)"', line)
        if not m:
            continue
        idx = int(m.group(1))
        if idx == 0:
            continue  # Clear Label / background
        r, g, b = int(m.group(2)), int(m.group(3)), int(m.group(4))
        desc = m.group(5).strip()
        lm = _LABEL_RE.match(desc)
        if lm:
            emapa = f"EMAPA:{lm.group(1)}"
            name = lm.group(2).strip()
        else:
            emapa, name = "", desc
        labels[idx] = Label(index=idx, rgb=(r, g, b), emapa=emapa, name=name)
    return labels


if __name__ == "__main__":
    import sys
    labs = parse_labels(sys.argv[1])
    print(f"{len(labs)} components")
    for idx in sorted(labs)[:10]:
        l = labs[idx]
        print(f"  {idx:4d}  rgb{l.rgb}  {l.emapa:14s} {l.name}")
