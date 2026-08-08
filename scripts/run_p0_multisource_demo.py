from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.editor import Asset, Clip, EDL, Target, render, technical_qc
manifest = json.loads((ROOT / "assets/source-footage/manifest.json").read_text())
assets = []
for item in manifest["assets"]:
    v, a = item["video"], item["audio"]
    n, d = str(v["fps"]).split("/")
    assets.append(Asset(Path(item["file"]).stem, str((ROOT / "assets/source-footage" / item["file"]).resolve()), item["duration_seconds"], v["width"], v["height"], float(n) / float(d), v["codec"], a["codec"], item["sha256"]))
by_id = {a.asset_id: a for a in assets}
ids = ["habib-jafar-pemuda-tersesat-biaya-admin", "habib-jafar-shopeepay-kirim-uang-gratis", "habib-jafar-iklan-shopeepay"]
clips = [
    Clip("hook", ids[0], 4.84, 7.84, 0.0, "hook", "visual cost conflict"),
    Clip("reaction", ids[1], 7.13, 10.13, 3.0, "reaction", "portrait visual reset"),
    Clip("payoff", ids[2], 12.45, 16.45, 6.0, "payoff", "campaign message"),
]
edl = EDL(1, "p0-multisource-demo", Target(), [by_id[x] for x in ids], clips, {"planner": "deterministic integration demo"})
out_dir = ROOT / "projects/p0-multisource-demo"
(out_dir / "edl").mkdir(parents=True, exist_ok=True)
(out_dir / "renders").mkdir(exist_ok=True)
(out_dir / "qc").mkdir(exist_ok=True)
(out_dir / "edl/edl_v1.json").write_text(json.dumps(edl.as_dict(), ensure_ascii=False, indent=2) + "\n")
output = render(edl, out_dir / "renders/draft_01.mp4", ROOT / "assets/source-footage/raw")
qc = technical_qc(output, "1080x1920", min_duration=9.9)
(out_dir / "qc/draft_01.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2) + "\n")
if not qc["passed"]:
    raise SystemExit(json.dumps(qc))
print(output)
print(json.dumps(qc))
