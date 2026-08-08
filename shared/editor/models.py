from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Asset:
    asset_id: str
    path: str
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str = ""
    audio_codec: str = ""
    sha256: str = ""
    transcript_path: str = ""
    analysis_path: str = ""


@dataclass(frozen=True)
class Clip:
    id: str
    asset_id: str
    source_in: float
    source_out: float
    timeline_start: float
    role: str = ""
    reason: str = ""
    transform: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.source_out - self.source_in


@dataclass(frozen=True)
class Target:
    resolution: str = "1080x1920"
    aspect_ratio: str = "9:16"
    fps: int = 30


@dataclass(frozen=True)
class EDL:
    version: int
    project_id: str
    target: Target
    assets: list[Asset]
    video: list[Clip]
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project_id": self.project_id,
            "target": asdict(self.target),
            "assets": [asdict(asset) for asset in self.assets],
            "tracks": {"video": [asdict(clip) for clip in self.video], "audio": [], "captions": [], "overlays": []},
            "metadata": self.metadata,
        }


def edl_from_dict(raw: dict[str, Any]) -> EDL:
    tracks = raw.get("tracks") or {}
    target = Target(**(raw.get("target") or {}))
    assets = [Asset(**item) for item in raw.get("assets", [])]
    clips = [Clip(**item) for item in tracks.get("video", [])]
    return EDL(
        version=int(raw.get("version", 1)),
        project_id=str(raw.get("project_id", "")),
        target=target,
        assets=assets,
        video=clips,
        metadata=raw.get("metadata") or {},
    )


def asset_from_manifest(item: dict[str, Any], root: Path, transcript_path: str = "", analysis_path: str = "") -> Asset:
    video = item.get("video") or {}
    audio = item.get("audio") or {}
    fps_raw = str(video.get("fps", "0/1"))
    numerator, _, denominator = fps_raw.partition("/")
    fps = float(numerator) / max(1.0, float(denominator or 1))
    return Asset(
        asset_id=Path(str(item["file"])).stem,
        path=str((root / str(item["file"])).resolve()),
        duration=float(item["duration_seconds"]),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        video_codec=str(video.get("codec", "")),
        audio_codec=str(audio.get("codec", "")),
        sha256=str(item.get("sha256", "")),
        transcript_path=transcript_path,
        analysis_path=analysis_path,
    )
