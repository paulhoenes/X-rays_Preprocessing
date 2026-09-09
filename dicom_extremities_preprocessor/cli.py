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
    p.add_argument("--view", default="dp", help="dp, oblique or lat")
    a = p.parse_args(argv)

    run(a.input, a.output, bodypart=a.bodypart, view=a.view)


if __name__ == "__main__":
    main()
