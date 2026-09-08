"""Command line entry point -- argument parsing only, no logic.

What is decided lives in ``rules.py`` and ``config/rules.yaml``, the order of
the steps in ``pipeline.py``.

    dicom-extremities-preprocessor --input /path/rawdata --output /path/target
    python -m dicom_extremities_preprocessor.cli --input ... --output ...
"""
from __future__ import annotations

import argparse

from .pipeline import run


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="dicom-extremities-preprocessor",
        description="Preprocess raw DICOMs: derive body part, side and view "
                    "from the header, invert MONOCHROME1, mirror right hands, "
                    "split bilateral images, pair the views.")
    p.add_argument("--input", required=True,
                   help="folder with the raw data (searched recursively, may "
                        "be read-only)")
    p.add_argument("--output", required=True,
                   help="target folder; gets dicoms/, csvs/ and provenance.json")
    p.add_argument("--rules", default=None,
                   help="own rules.yaml; otherwise the bundled one")
    p.add_argument("--bodypart", default="H",
                   help="selection: H, F or O (default: H)")
    p.add_argument("--views", default="dp,oblique",
                   help="views, comma separated: dp, oblique, lat "
                        "(default: dp,oblique)")
    p.add_argument("--keep-unpaired", action="store_true",
                   help="also keep cases where a view is missing "
                        "(default: complete pairs only)")
    p.add_argument("--overwrite", action="store_true",
                   help="rewrite existing result files instead of skipping "
                        "them")
    a = p.parse_args(argv)

    run(a.input, a.output,
        rules=a.rules,
        bodypart=a.bodypart,
        views=tuple(v.strip() for v in a.views.split(",") if v.strip()),
        overwrite=a.overwrite,
        drop_unpaired=not a.keep_unpaired)


if __name__ == "__main__":
    main()
