"""Validated EDL-driven multi-source editor foundation."""

from .models import Asset, Clip, EDL, Target, asset_from_manifest, edl_from_dict
from .edl import EDLValidationError, validate
from .executor import render
from .qc import technical_qc

__all__ = [
    "Asset", "Clip", "EDL", "Target", "asset_from_manifest", "edl_from_dict",
    "EDLValidationError", "validate", "render", "technical_qc",
]
