"""What gets decided: body part, side, view and photometry.

The matching and the text normalisation it runs against live here too --
they exist for these rules and nothing else.
"""
import importlib.resources
import re
import unicodedata

import numpy as np
import pandas as pd
import yaml


with importlib.resources.open_text("dicom_extremities_preprocessor.resources",
                                   "mappings_regex.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)["categories"]


def add_InfosViaRegEx(df, cfg=cfg):
    """Add bodypart_new, laterality_new, view_position_new and
    photometric_interpretation_new, falling back to the free text fields.

    Column names are the ones the pipeline reads from the DICOM tags.
    """
    # --- Bodypart ---
    categorize_column_regex(
        df, 'bodypart_new', 'body_part_examined', cfg['bodypart'],
        fallbacks=[('study_description', cfg['study_description_bodypart']),
                   ('series_description', cfg['series_description_bodypart'])])
    df['bodypart_new'] = df['bodypart_new'].map({'foot': 'F', 'hand': 'H',
                                                 'other': 'O'})

    # --- Laterality ---
    categorize_column_regex(
        df, 'laterality_new', 'laterality', cfg['laterality'],
        fallbacks=[('view_position', cfg['view_position_laterality']),
                   ('series_description', cfg['series_description_laterality'])])

    # --- View position ---
    categorize_column_regex(
        df, 'view_position_new', 'view_position', cfg['view_position_viewposition'],
        fallbacks=[('series_description', cfg['series_description_viewposition'])])

    # --- Photometric ---
    categorize_column_regex(
        df, 'photometric_interpretation_new', 'photometric_interpretation',
        cfg['photometric'])
    return df


def normalize_text(x):
    if pd.isna(x):
        return "" #np.nan

    x = str(x)
    x = unicodedata.normalize("NFKC", x)
    x = x.lower().strip()

    # Umlaute / deutsche Sonderzeichen
    x = (
        x.replace("ß", "ss")
         .replace("ä", "ae")
         .replace("ö", "oe")
         .replace("ü", "ue")
    )

    # Häufige Encoding-Probleme in deinem Datensatz
    x = x.replace("fu?", "fuss")
    x = x.replace("vorfu?", "vorfuss")
    x = x.replace("schr?g", "schraeg")
    x = x.replace("extremit?ten", "extremitaeten")

    # Interpunktion teilweise vereinheitlichen, aber / behalten
    x = re.sub(r"[.,;:]+", " ", x)
    x = re.sub(r"\s+", " ", x)

    return x


def categorize_column_regex(
    df,
    target_col,
    primary_tag,
    mapping_regex,
    fallbacks=None,
):
    """
    Kategorisierung mit Regex.
    Die Reihenfolge der Labels im YAML bestimmt die Priorität.
    """

    #df[target_col] = np.nan
    df[target_col] = pd.Series(pd.NA, index=df.index, dtype="object")

    def apply_rules(source_col, rules, only_empty=True):
        source_norm = df[source_col].map(normalize_text)

        # Wichtig: Reihenfolge aus YAML wird übernommen
        for label, patterns in rules.items():
            pattern = "|".join(patterns)

            match_mask = source_norm.str.contains(
                pattern,
                regex=True,
                na=False
            )

            if only_empty:
                match_mask = df[target_col].isna() & match_mask

            df.loc[match_mask, target_col] = label

    # Priority 1: primary DICOM tag
    apply_rules(primary_tag, mapping_regex, only_empty=True)

    # Priority 2: fallback columns, nur noch NaN-Zeilen
    if fallbacks:
        for col, fallback_mapping in fallbacks:
            if not df[target_col].isna().any():
                break

            apply_rules(col, fallback_mapping, only_empty=True)

    return df
