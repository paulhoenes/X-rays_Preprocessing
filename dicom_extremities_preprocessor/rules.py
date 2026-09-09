"""Derive body part, side and view from the DICOM header.

All selection logic lives here. ``cli.py`` only parses arguments,
``pipeline.py`` only runs the steps -- what is *decided* is decided in this
file and in ``config/rules.yaml``.

The basic problem: the headers are incomplete and partly plain wrong. Three
findings from a tag inventory over the whole cohort (17,038 files):

1. ``ViewPosition`` lies for hands. Zither/Norgaard images carry ``AP``, so
   the tag claims PA. ``LLO``/``RLO`` never occur for hands, only for feet.
2. ``BodyPartExamined`` is often a station default. Foot, knee and cervical
   spine images carry ``HAND`` here.
3. 27 % of the images have no ``ViewPosition`` tag at all.

Hence the priority that ``categorize`` applies:

    body part   free text beats tag
    view        free text for hands, tag otherwise
    side        tag first, then free text

All text rules live in ``config/rules.yaml`` and run against
``normalize_text``.
"""


from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

RULES = Path(__file__).parent / "config" / "rules.yaml"

# Free text fields, most reliable first. The series description names the
# single image, the study description only the whole visit.
TEXT_FIELDS = ("series_description", "study_description")


def load_rules(path=None) -> dict:
    """Load the rule set (default: the bundled ``config/rules.yaml``)."""
    with open(path or RULES, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------ Text normalization

def normalize_text(x) -> str:
    """Bring text into the form the patterns in rules.yaml run against.

    Lower case, NFKC normalized, German umlauts spelled out (ae/oe/ue/ss),
    punctuation turned into spaces, runs of whitespace collapsed. Missing
    values become the empty string. Patterns therefore have to be written in
    lower case and without umlauts.
    """
    if pd.isna(x):
        return ""
    x = unicodedata.normalize("NFKC", str(x)).lower().strip()
    x = (x.replace("ß", "ss").replace("ä", "ae")
          .replace("ö", "oe").replace("ü", "ue"))
    x = re.sub(r"[.,;:]+", " ", x)
    # strip again at the end: the punctuation above turns into spaces, and a
    # trailing one would break the patterns anchored with ^...$
    return re.sub(r"\s+", " ", x).strip()


def _first_match(text: pd.Series, rules: dict) -> pd.Series:
    """First label whose pattern matches -- NA otherwise.

    The label order in rules.yaml is the priority: "oblique" before "lat",
    otherwise the pattern for ``ll`` already swallows the ``llo``.
    """
    result = pd.Series(pd.NA, index=text.index, dtype="object")
    for label, patterns in rules.items():
        open_rows = result.isna()
        if not open_rows.any():
            break
        hit = text.str.contains("|".join(patterns), regex=True, na=False)
        result[open_rows & hit] = label
    return result


def _coalesce(*columns: pd.Series) -> pd.Series:
    """Walk the columns in order and take the first value that is set."""
    result = columns[0].copy()
    for other in columns[1:]:
        result = result.where(result.notna(), other)
    return result


# ------------------------------------------------------------------ Categorize

def categorize(df: pd.DataFrame, rules: dict, log=None) -> pd.DataFrame:
    """Set body part, side, view, photometry and file name.

    Adds the columns ``bodypart_new``, ``laterality_new``,
    ``view_position_new``, ``photometric_interpretation_new`` and
    ``filename_new``. Without ``log`` the messages stay quiet -- so the
    function can also be called from a notebook.
    """
    log = log or logging.getLogger(__name__)
    df = df.copy()
    norm = {field: df[field].map(normalize_text) if field in df
                   else pd.Series("", index=df.index)
            for field in TEXT_FIELDS}

    # --- body part: free text beats tag -----------------------------------
    # Reason: see module header (2). The series description names the single
    # image and is closer to the truth than a tag the device copies from the
    # examination protocol.
    from_tag = _first_match(df["body_part_examined"].map(normalize_text),
                            rules["bodypart"]["tag"])
    from_text = _coalesce(*(_first_match(norm[f], rules["bodypart"]["text"])
                            for f in TEXT_FIELDS))
    conflicts = int((from_tag.notna() & from_text.notna()
                     & (from_tag.fillna("") != from_text.fillna(""))).sum())
    df["bodypart_new"] = (_coalesce(from_text, from_tag)
                          .map({"foot": "F", "hand": "H", "other": "O"}))
    if conflicts:
        log.info(f"body part: {conflicts} images where the free text "
                 f"contradicts the tag -- the free text wins")

    # --- drop hand images without finger joints ---------------------------
    # Wrist, forearm, single fingers: they carry BodyPartExamined = HAND but
    # do not show the joints that are meant to be scored.
    no_joint = "|".join(rules["hand"]["no_joint_image"])
    drop = (df["bodypart_new"].eq("H")
            & pd.concat([norm[f].str.contains(no_joint, regex=True, na=False)
                         for f in TEXT_FIELDS], axis=1).any(axis=1))
    df.loc[drop, "bodypart_new"] = "O"
    if drop.any():
        log.info(f"{int(drop.sum())} images without a whole hand "
                 f"(wrist/forearm/finger) taken out of the hand category")

    # --- side: tag first --------------------------------------------------
    # Laterality is reliable in this cohort; where it is missing, ViewPosition
    # names the side as well (LL/RL/LLO/RLO), free text last.
    df["laterality_new"] = _coalesce(
        _first_match(df["laterality"].map(normalize_text), rules["laterality"]["tag"]),
        _first_match(df["view_position"].map(normalize_text), rules["laterality"]["view_tag"]),
        _first_match(norm["series_description"], rules["laterality"]["text"]))

    # --- view: free text for hands, tag otherwise -------------------------
    # Reason: see module header (1). Only the series description, explicitly
    # not the study description: that one names the whole visit ("Hand dp
    # Zitherstellung" = both views were taken) and would mark the dp images of
    # such visits as oblique too.
    view_tag = _first_match(df["view_position"].map(normalize_text), rules["view"]["tag"])
    view_text = _first_match(norm["series_description"], rules["view"]["text"])
    is_hand = df["bodypart_new"].eq("H")
    df["view_position_new"] = _coalesce(view_tag, view_text).where(
        ~is_hand, _coalesce(view_text, view_tag))

    if rules["hand"]["lat_is_oblique"]:
        # For hands "lat"/"seitl." is in fact the oblique view -- confirmed
        # visually, see rules.yaml. For feet this does not hold.
        as_oblique = is_hand & df["view_position_new"].eq("lat")
        df.loc[as_oblique, "view_position_new"] = "oblique"
        if as_oblique.any():
            log.info(f"{int(as_oblique.sum())} hand images with 'lat'/'seitl.' "
                     f"counted as oblique")
    disagree = int((is_hand & view_tag.notna() & view_text.notna()
                    & (view_tag.fillna("") != view_text.fillna(""))).sum())
    if disagree:
        log.info(f"view: {disagree} hand images where ViewPosition "
                 f"contradicts the free text -- the free text wins")

    # --- photometry -------------------------------------------------------
    df["photometric_interpretation_new"] = _first_match(
        df["photometric_interpretation"].map(normalize_text),
        rules["photometric"]["tag"])

    cols = ["bodypart_new", "laterality_new", "view_position_new",
            "photometric_interpretation_new"]
    df[cols] = df[cols].fillna("NaN")
    df["filename_new"] = (df["pat_id"].astype(str) + "_"
                          + df["study_date"].astype(str) + "_"
                          + df["bodypart_new"] + "_" + df["laterality_new"] + "_"
                          + df["view_position_new"] + "_"
                          + df["photometric_interpretation_new"])

    log.info("categories derived: "
             + ", ".join(f"{c.replace('_new', '')}={df[c].ne('NaN').sum()}/{len(df)}"
                         for c in cols))
    return df


def select(df: pd.DataFrame, log=None, bodypart="H", view="dp") -> pd.DataFrame:
    """Filter down to the subset of interest and number the duplicates.

    Images without a recognized side drop out. They are unusable: pairing runs
    over (pat_id, study_date, side), and the score table lists every joint
    separately for left and right -- without a side there is neither a
    counterpart nor a label. They used to be written out and paired with each
    other under the side "NaN".
    """
    log = log or logging.getLogger(__name__)
    sel = df[(df["bodypart_new"] == bodypart)
             & (df["view_position_new"] == view)].copy()

    has_side = sel["laterality_new"].isin(["L", "R", "B"])
    if (~has_side).any():
        log.info(f"  {int((~has_side).sum())} images without a recognized "
                 f"side skipped")
        sel = sel[has_side]

    sel["dup_suffix"] = sel.groupby("filename_new").cumcount().astype(str)
    sel["filename_new_dupl"] = sel["filename_new"] + "_" + sel["dup_suffix"]
    log.info(f"selection {bodypart}/{view}: {len(sel)} of {len(df)} images")
    return sel


def rebuild_filename(row) -> str:
    """File name from the categories -- rebuild after every change to them."""
    return (f"{row['pat_id']}_{row['study_date']}_{row['bodypart_new']}_"
            f"{row['laterality_new']}_{row['view_position_new']}_"
            f"{row['photometric_interpretation_new']}_{row['dup_suffix']}")
