from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from shared.editor import Asset, Clip, EDL, EDLValidationError, Target, technical_qc, validate
from shared.editor.edl import move_clip, split_clip, trim_clip

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "assets/source-footage/raw"
MANIFEST = json.loads((ROOT / "assets/source-footage/manifest.json").read_text())


def assets() -> list[Asset]:
    result = []
    for item in MANIFEST["assets"][:3]:
        video, audio = item["video"], item["audio"]
        n, d = str(video["fps"]).split("/")
        result.append(Asset(Path(item["file"]).stem, str((ROOT / "assets/source-footage" / item["file"]).resolve()), item["duration_seconds"], video["width"], video["height"], float(n) / float(d), video["codec"], audio["codec"], item["sha256"]))
    return result


def edl() -> EDL:
    a = assets()
    clips = [
        Clip("a", a[0].asset_id, 1, 3, 0, "hook"),
        Clip("b", a[1].asset_id, 2, 4, 2, "reaction"),
        Clip("c", a[2].asset_id, 1, 4, 4, "payoff"),
    ]
    return EDL(1, "p0-test", Target(), a, clips)


class EditorP0Tests(unittest.TestCase):
    def test_valid_multisource_edl(self):
        validate(edl(), RAW)

    def test_reject_negative_timestamp(self):
        base = edl(); broken = replace(base, video=[replace(base.video[0], source_in=-1), *base.video[1:]])
        with self.assertRaises(EDLValidationError): validate(broken, RAW)

    def test_reject_end_before_start(self):
        base = edl(); broken = replace(base, video=[replace(base.video[0], source_out=.5), *base.video[1:]])
        with self.assertRaises(EDLValidationError): validate(broken, RAW)

    def test_reject_unknown_asset(self):
        base = edl(); broken = replace(base, video=[replace(base.video[0], asset_id="nope"), *base.video[1:]])
        with self.assertRaises(EDLValidationError): validate(broken, RAW)

    def test_reject_past_duration(self):
        base = edl(); broken = replace(base, video=[replace(base.video[0], source_out=999), *base.video[1:]])
        with self.assertRaises(EDLValidationError): validate(broken, RAW)

    def test_operations_keep_timeline_contiguous(self):
        base = edl(); changed = trim_clip(base, "a", 1.2, 2.5); changed = split_clip(changed, "b", 3); changed = move_clip(changed, "c", 0)
        validate(changed, RAW)


if __name__ == "__main__":
    unittest.main()
