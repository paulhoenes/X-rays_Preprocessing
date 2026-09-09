"""Preprocessing of extremity X-rays (hands, feet) from raw DICOM data.

``visualize`` is not imported here on purpose -- it needs matplotlib, which
is an optional dependency. Import it explicitly where it is used.
"""

from __future__ import annotations

from . import header, pipeline, pixels, rules, utils
from .pipeline import run

__version__ = "0.1.0"
