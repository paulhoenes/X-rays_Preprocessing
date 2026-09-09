### The processing steps - 5 steps + pairing of the views

"""
    1. read the header of every file           header.scan_metadata
    2. derive categories, build file names     rules.categorize
    3. filter by body part / view              rules.select
    3b. detect bilateral images on the image   pixels.detect_bilateral
    4. standardize the pixels and store them   pixels.write_processed
    5. pair PA and oblique into cases          build_pairs

Step 3b is the only one that decides on the pixels instead of the header --
because the header simply does not say whether two hands lie on the image.

``scan`` stops after step 2: headers and categories, nothing written.

What is *decided* is decided in ``rules.py`` and ``config/rules.yaml`` --
here is only the order in which it happens and what gets recorded.
"""
from __future__ import annotations

import datetime
import json
import logging
import sys
from pathlib import Path

import pandas as pd
import pydicom

from . import __version__
from .header import scan_metadata
from .pixels import detect_bilateral, write_processed
from .rules import RULES, categorize, load_rules, select
from .utils import get_unique_metadata, setup_logger


def build_pairs(dfs_by_view: dict, log) -> pd.DataFrame:
    """Bring PA and oblique together into cases.

    For the multi-view work the unit is not the single image but the *case*:
    one hand at one visit, in both views. The pairing key is therefore
    (pat_id, study_date, side).

    Pairing happens AFTER writing, not before: bilateral images are split into
    L and R only while writing, before that their side is not a real side yet.

    Result: one row per case, one column per view holding the written file name
    (empty if the view is missing), plus ``status``.
    """
    key = ["pat_id", "study_date", "laterality_new"]
    rows = None
    for view, df in dfs_by_view.items():
        if df.empty:
            continue
        # One hand can have several images of the same view at one visit
        # (repeats, duplicates). Deterministically take the first.
        part = (df.sort_values("filename_written")
                  .groupby(key, as_index=False)
                  .first()[key + ["filename_written"]]
                  .rename(columns={"filename_written": f"file_{view}"}))
        rows = part if rows is None else rows.merge(part, on=key, how="outer")
    if rows is None:
        return pd.DataFrame(columns=key + ["status"])

    cols = [f"file_{v}" for v in dfs_by_view]
    for c in cols:
        if c not in rows:
            rows[c] = pd.NA
    complete = rows[cols].notna().all(axis=1)
    rows["status"] = complete.map({True: "complete", False: "incomplete"})

    log.info(f"pairing: {int(complete.sum())} complete of "
             f"{len(rows)} (pat_id, study_date, side) cases")
    for c in cols:
        log.info(f"  {c}: {int(rows[c].notna().sum())} present")
    return rows.sort_values(key).reset_index(drop=True)


def scan(input_dir, rules=None, log=None) -> pd.DataFrame:
    """Steps 1 and 2 only: read the headers, derive the categories.

    Touches no pixel and writes no file -- for looking at a data set before
    deciding to process it, and for counting how the rules fall out on a new
    cohort. The result is the same table ``run`` writes as
    ``csvs/step2_categories.csv``.

        df = scan("/path/rawdata")
        df.groupby(["bodypart_new", "view_position_new"]).size()

    ``get_unique_metadata`` on the same table shows what the free text fields
    contain -- the basis for new patterns in ``rules.yaml``.
    """
    log = log or logging.getLogger(__name__)
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"source folder not found: {input_dir}")

    cfg = load_rules(rules)
    return categorize(scan_metadata(input_dir, cfg["tags"], log), cfg, log)


def run(input_dir, output_dir, rules=None, bodypart="H",
        views=("dp", "oblique"), overwrite=False, drop_unpaired=True) -> Path:
    """The complete preprocessing. Returns the folder with the DICOMs.

    Both views are produced in ONE run and in separate folders -- the landmark
    models are view specific. Cases with a missing view are removed by default,
    so that the plain PA baseline and the fusion model train on the same cases;
    otherwise the comparison would be unfair.

    Creates below ``output_dir``::

        dicoms/<view>/        the processed images, one folder per view
        csvs/                 the tables of every intermediate step
        csvs/pairs.csv        the pairing PA <-> oblique
        provenance.json       what produced this data state
        pipeline_<time>.log   log of the run
    """
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"source folder not found: {input_dir}")

    csv_dir, dicom_dir = output_dir / "csvs", output_dir / "dicoms"
    csv_dir.mkdir(parents=True, exist_ok=True)
    log = setup_logger(str(output_dir))
    start = datetime.datetime.now()

    log.info(f"source: {input_dir}")
    log.info(f"target: {output_dir}")
    cfg = load_rules(rules)

    df = scan_metadata(input_dir, cfg["tags"], log)
    df.to_csv(csv_dir / "step1_metadata_df.csv", index=False)
    get_unique_metadata(df, ["filename_old", "filepathname_old", "columns",
                             "rows", "pat_id", "study_date"]
                        ).to_csv(csv_dir / "step1_unique_values.csv", index=False)

    df2 = categorize(df, cfg, log)
    df2.to_csv(csv_dir / "step2_categories.csv", index=False)

    selected_by_view, written_by_view = {}, {}
    for v in views:
        sel = select(df2, log, bodypart=bodypart, view=v)
        sel = detect_bilateral(sel, cfg, log)
        sel.to_csv(csv_dir / f"step3_selected_{v}.csv", index=False)
        written = write_processed(sel, dicom_dir / v, log, overwrite=overwrite)
        written.to_csv(csv_dir / f"step4_written_{v}.csv", index=False)
        selected_by_view[v], written_by_view[v] = sel, written

    pairs = build_pairs(written_by_view, log)
    pairs.to_csv(csv_dir / "pairs.csv", index=False)

    removed = 0
    if drop_unpaired and len(pairs):
        incomplete = pairs[pairs["status"] != "complete"]
        for _, row in incomplete.iterrows():
            for v in views:
                name = row.get(f"file_{v}")
                dest = dicom_dir / v / name if isinstance(name, str) else None
                if dest is not None and dest.exists():
                    dest.unlink()
                    removed += 1
        log.info(f"{removed} images without a counterpart removed "
                 f"({len(incomplete)} incomplete cases)")

    # What produced this data state? Without this file it cannot be
    # reconstructed later.
    complete = int((pairs["status"] == "complete").sum()) if len(pairs) else 0
    provenance = {
        "created": start.isoformat(timespec="seconds"),
        "duration_seconds": round((datetime.datetime.now() - start).total_seconds()),
        "package_version": __version__,
        "python": sys.version.split()[0],
        "pydicom": pydicom.__version__,
        "source": str(input_dir),
        "rules": str(rules or RULES),
        "selection": {"bodypart": bodypart, "views": list(views)},
        "complete_pairs_only": bool(drop_unpaired),
        "files_read": int(len(df)),
        "files_selected": {v: int(len(d)) for v, d in selected_by_view.items()},
        "files_written": {v: len(list((dicom_dir / v).glob("*.dcm")))
                          for v in views},
        "cases_total": int(len(pairs)),
        "cases_complete": complete,
        "in_container": Path("/.singularity.d").exists(),
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))

    log.info(f"done in {provenance['duration_seconds']}s -- "
             f"{complete} complete cases in {dicom_dir}")
    return dicom_dir
