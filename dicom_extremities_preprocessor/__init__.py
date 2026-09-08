"""Preprocessing of extremity X-rays (hands, feet) from raw DICOM data.

    pipeline.py    the order of the steps: run()
    rules.py       what gets decided: body part, side, view
    header.py      reading DICOM headers, without the pixels
    pixels.py      everything that touches the pixel data
    utils.py       logging and a helper for writing new rules
    cli.py         command line
    visualize.py   image grids for checking by eye (optional)

    config/rules.yaml   the only configuration file

Usage::

    import dicom_extremities_preprocessor as pp
    pp.run(input_dir, output_dir)

``visualize`` is not imported here on purpose -- it needs matplotlib, which is
an optional dependency. Import it explicitly where it is used::

    from dicom_extremities_preprocessor import visualize
"""
from __future__ import annotations

__version__ = "0.3.0"          # before the imports: pipeline.py reads it on load

from . import header, pipeline, pixels, rules, utils
from .pipeline import run

__all__ = ["header", "pipeline", "pixels", "rules", "utils", "run", "__version__"]
