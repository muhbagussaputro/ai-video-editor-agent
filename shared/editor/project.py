from __future__ import annotations

import json
from pathlib import Path

from .models import EDL, edl_from_dict
from .edl import validate
from .executor import render
from .qc import technical_qc


def render_project(raw_edl: dict, projects_root: Path, assets_root: Path) -> dict:
    edl: EDL = edl_from_dict(raw_edl)
    validate(edl, assets_root)
    root = projects_root / edl.project_id
    edl_dir, render_dir, qc_dir = root / "edl", root / "renders", root / "qc"
    for directory in (edl_dir, render_dir, qc_dir): directory.mkdir(parents=True, exist_ok=True)
    version = edl.version
    edl_path = edl_dir / f"edl_v{version}.json"
    output = render_dir / f"draft_{version:02d}.mp4"
    qc_path = qc_dir / f"draft_{version:02d}.json"
    edl_path.write_text(json.dumps(edl.as_dict(), ensure_ascii=False, indent=2) + "\n")
    render(edl, output, assets_root)
    qc = technical_qc(output, edl.target.resolution)
    qc_path.write_text(json.dumps(qc, ensure_ascii=False, indent=2) + "\n")
    return {"project_id": edl.project_id, "edl": str(edl_path), "render": str(output), "qc": str(qc_path), "passed": qc["passed"]}
