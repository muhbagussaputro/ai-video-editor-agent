from __future__ import annotations

from pathlib import Path

from .models import EDL

ROLES = {"hook", "setup", "problem", "curiosity", "explanation", "proof", "demo", "reaction", "payoff", "cta", "broll"}


class EDLValidationError(ValueError):
    pass


def validate(edl: EDL, allowed_root: Path) -> None:
    if edl.version != 1 or not edl.project_id:
        raise EDLValidationError("EDL requires version=1 and project_id")
    try:
        width, height = (int(x) for x in edl.target.resolution.split("x", 1))
    except Exception as exc:
        raise EDLValidationError("invalid target resolution") from exc
    if width <= 0 or height <= 0 or edl.target.fps <= 0:
        raise EDLValidationError("invalid target")
    root = allowed_root.resolve()
    assets = {asset.asset_id: asset for asset in edl.assets}
    if not assets or not edl.video:
        raise EDLValidationError("EDL needs assets and video clips")
    expected = 0.0
    seen: set[str] = set()
    for clip in sorted(edl.video, key=lambda x: x.timeline_start):
        if clip.id in seen:
            raise EDLValidationError(f"duplicate clip id: {clip.id}")
        seen.add(clip.id)
        asset = assets.get(clip.asset_id)
        if not asset:
            raise EDLValidationError(f"unknown asset: {clip.asset_id}")
        path = Path(asset.path).resolve()
        if root not in path.parents or not path.is_file():
            raise EDLValidationError(f"asset outside root or missing: {asset.asset_id}")
        if clip.source_in < 0 or clip.source_out <= clip.source_in or clip.source_out > asset.duration + .05:
            raise EDLValidationError(f"invalid source range: {clip.id}")
        if clip.timeline_start < 0 or abs(clip.timeline_start - expected) > .02:
            raise EDLValidationError(f"timeline must be contiguous: {clip.id}")
        if clip.role and clip.role not in ROLES:
            raise EDLValidationError(f"invalid role: {clip.role}")
        expected += clip.duration


def timeline_duration(edl: EDL) -> float:
    return sum(clip.duration for clip in edl.video)


def add_clip(edl: EDL, clip) -> EDL:
    from dataclasses import replace
    clips = [*edl.video, clip]
    return replace(edl, video=clips)


def remove_clip(edl: EDL, clip_id: str) -> EDL:
    from dataclasses import replace
    clips = [clip for clip in edl.video if clip.id != clip_id]
    position = 0.0
    normalized = []
    for clip in clips:
        normalized.append(replace(clip, timeline_start=position)); position += clip.duration
    return replace(edl, video=normalized)


def replace_clip(edl: EDL, clip_id: str, replacement) -> EDL:
    from dataclasses import replace
    return replace(edl, video=[replacement if clip.id == clip_id else clip for clip in edl.video])


def move_clip(edl: EDL, clip_id: str, index: int) -> EDL:
    from dataclasses import replace
    clips = list(edl.video); clip = next(c for c in clips if c.id == clip_id); clips.remove(clip); clips.insert(index, clip)
    pos = 0.0; normalized=[]
    for item in clips: normalized.append(replace(item, timeline_start=pos)); pos += item.duration
    return replace(edl, video=normalized)


def trim_clip(edl: EDL, clip_id: str, source_in: float, source_out: float) -> EDL:
    from dataclasses import replace
    clips=[]; pos=0.0
    for clip in edl.video:
        item = replace(clip, source_in=source_in, source_out=source_out) if clip.id == clip_id else clip
        item = replace(item, timeline_start=pos); pos += item.duration; clips.append(item)
    return replace(edl, video=clips)


def split_clip(edl: EDL, clip_id: str, source_at: float) -> EDL:
    from dataclasses import replace
    clips=[]; pos=0.0
    for clip in edl.video:
        items=[clip]
        if clip.id == clip_id:
            if not clip.source_in < source_at < clip.source_out: raise EDLValidationError("split outside clip")
            items=[replace(clip,id=f"{clip.id}_a",source_out=source_at),replace(clip,id=f"{clip.id}_b",source_in=source_at)]
        for item in items: clips.append(replace(item,timeline_start=pos)); pos += item.duration
    return replace(edl, video=clips)

reorder_clips = move_clip
