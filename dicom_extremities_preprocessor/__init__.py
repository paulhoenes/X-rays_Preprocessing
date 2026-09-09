"""Preprocessing of extremity X-rays (hands, feet) from raw DICOM data.

``visualize`` is not imported here on purpose -- it needs matplotlib, which
is an optional dependency. Import it explicitly where it is used.
"""
from __future__ import annotations

__version__ = "0.1.0"          # before the imports: pipeline.py reads it on load

from . import header, pipeline, pixels, rules, utils
from .pipeline import run, scan
from .utils import get_unique_metadata

__all__ = ["header", "pipeline", "pixels", "rules", "utils",
           "run", "scan", "get_unique_metadata", "__version__"]
