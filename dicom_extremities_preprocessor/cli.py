"""Command line entry point -- argument parsing only, no logic.

    dicom-extremities-preprocessor --input /path/rawdata --output /path/target
"""
import argparse

from .pipeline import run


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="dicom-extremities-preprocessor",
        description="Preprocess raw DICOMs: derive body part, side and view "
                    "from the header, invert MONOCHROME1, mirror right hands, "
                    "split bilateral images.")
    p.add_argument("--input", required=True,
                   help="folder with the raw data (searched recursively)")
    p.add_argument("--output", required=True, help="target folder")
    p.add_argument("--bodypart", default="H", help="H hand, F foot, O other")
    p.add_argument("--views", default="dp,oblique",
                   help="views, comma separated: dp, oblique, lat")
    p.add_argument("--keep-unpaired", action="store_true",
                   help="also keep cases where a view is missing")
    p.add_argument("--overwrite", action="store_true",
                   help="rewrite existing result files instead of skipping them")
    a = p.parse_args(argv)

    run(a.input, a.output, bodypart=a.bodypart,
        views=tuple(v.strip() for v in a.views.split(",") if v.strip()),
        overwrite=a.overwrite, drop_unpaired=not a.keep_unpaired)


if __name__ == "__main__":
    main()
