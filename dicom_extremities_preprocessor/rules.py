"""What gets decided: body part, side, view and photometry.

The matching and the text normalisation it runs against live here too --
they exist for these rules and nothing else.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

RULES = Path(__file__).parent / "config" / "rules.yaml"

# Free text fields, most reliable first. The series description names the
# single image, the study description only the whole visit.
TEXT_FIELDS = ("series_description", "study_description")


def load_rules(path=None) -> dict:
    """Load the rule set (default: the bundled config/rules.yaml)."""
    with open(path or RULES, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["categories"]


def normalize_text(x) -> str:
    """Bring text into the form the patterns in rules.yaml run against."""
    if pd.isna(x):
        return ""
    x = unicodedata.normalize("NFKC", str(x)).lower().strip()
    x = (x.replace("ß", "ss").replace("ä", "ae")
          .replace("ö", "oe").replace("ü", "ue"))
    x = re.sub(r"[.,;:]+", " ", x)
    return re.sub(r"\s+", " ", x)


def _first_match(text: pd.Series, rules: dict) -> pd.Series:
    """First label whose pattern matches -- NA otherwise.

    The label order in rules.yaml is the priority: "oblique" before "lat",
    otherwise the pattern for ll already swallows the llo.
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


def categorize(df: pd.DataFrame, rules: dict, log=None) -> pd.DataFrame:
    """Set body part, side, view, photometry and file name.

    Each category is taken from its DICOM tag first and from the free text
    fields only where the tag says nothing.
    """
    log = log or logging.getLogger(__name__)
    df = df.copy()
    tag = {c: df[c].map(normalize_text) for c in
           ("body_part_examined", "laterality", "view_position",
            "photometric_interpretation")}
    text = {c: df[c].map(normalize_text) for c in
            ("series_description", "study_description")}

    # --- body part: free text beats tag -----------------------------------
    # BodyPartExamined is often a station default: in this cohort foot, knee
    # and cervical spine images carry HAND. The description names the single
    # image and is closer to the truth.
    from_tag = _first_match(tag["body_part_examined"], rules["bodypart"]["tag"])
    from_text = _coalesce(*(_first_match(text[f], rules["bodypart"]["text"])
                            for f in TEXT_FIELDS))
    conflicts = int((from_tag.notna() & from_text.notna()
                     & (from_tag.fillna("") != from_text.fillna(""))).sum())
    df["bodypart_new"] = (_coalesce(from_text, from_tag)
                          .map({"foot": "F", "hand": "H", "other": "O"}))
    if conflicts:
        log.info(f"body part: {conflicts} images where the free text "
                 f"contradicts the tag -- the free text wins")

    # --- side -------------------------------------------------------------
    df["laterality_new"] = _coalesce(
        _first_match(tag["laterality"], rules["laterality"]),
        _first_match(tag["view_position"], rules["view_position_laterality"]),
        _first_match(text["series_description"], rules["series_description_laterality"]),
    )

    # --- view -------------------------------------------------------------
    df["view_position_new"] = _coalesce(
        _first_match(tag["view_position"], rules["view_position_viewposition"]),
        _first_match(text["series_description"], rules["series_description_viewposition"]),
    )

    # --- photometry -------------------------------------------------------
    df["photometric_interpretation_new"] = _first_match(
        tag["photometric_interpretation"], rules["photometric"])

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


def rebuild_filename(row) -> str:
    """File name from the categories -- rebuild after every change to them."""
    return (f"{row['pat_id']}_{row['study_date']}_{row['bodypart_new']}_"
            f"{row['laterality_new']}_{row['view_position_new']}_"
            f"{row['photometric_interpretation_new']}_{row['dup_suffix']}")
