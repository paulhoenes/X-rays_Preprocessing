"""Command line entry point -- argument parsing only, no logic.

What is decided lives in ``rules.py`` and ``config/rules.yaml``, the order of
the steps in ``pipeline.py``.

    dicom-extremities-preprocessor --input /path/rawdata --output /path/target
    python -m dicom_extremities_preprocessor.cli --input ... --output ...

``--scan-only`` stops after the header analysis and writes no image:

    dicom-extremities-preprocessor --input /path/rawdata --scan-only
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from .pipeline import run, scan


def _summarize(df: pd.DataFrame) -> None:
    """Print how the rules fall out -- one table, no files."""
    print(f"\n{len(df)} headers read\n")
    counts = pd.crosstab(df["bodypart_new"], df["view_position_new"],
                         margins=True, margins_name="total")
    print("body part x view")
    print(counts.to_string(), "\n")
    print("side")
    print(df["laterality_new"].value_counts().to_string(), "\n")
    print("photometry")
    print(df["photometric_interpretation_new"].value_counts().to_string())


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="dicom-extremities-preprocessor",
        description="Preprocess raw DICOMs: derive body part, side and view "
                    "from the header, invert MONOCHROME1, mirror right hands, "
                    "split bilateral images, pair the views.")
    p.add_argument("--input", required=True,
                   help="folder with the raw data (searched recursively, may "
                        "be read-only)")
    p.add_argument("--output",
                   help="target folder; gets dicoms/, csvs/ and provenance.json. "
                        "Required unless --scan-only is given, where it only "
                        "takes the table")
    p.add_argument("--scan-only", action="store_true",
                   help="read the headers and derive the categories, then stop: "
                        "no pixels touched, no image written. Prints a summary "
                        "and, with --output, the table as step2_categories.csv")
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

    if a.scan_only:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        df = scan(a.input, rules=a.rules)
        _summarize(df)
        if a.output:
            out = Path(a.output) / "csvs"
            out.mkdir(parents=True, exist_ok=True)
            df.to_csv(out / "step2_categories.csv", index=False)
            print(f"\nwritten: {out / 'step2_categories.csv'}")
        return

    if not a.output:
        p.error("--output is required (or use --scan-only)")

    run(a.input, a.output,
        rules=a.rules,
        bodypart=a.bodypart,
        views=tuple(v.strip() for v in a.views.split(",") if v.strip()),
        overwrite=a.overwrite,
        drop_unpaired=not a.keep_unpaired)


if __name__ == "__main__":
    main()
