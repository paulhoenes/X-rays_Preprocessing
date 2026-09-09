"""Derive body part, side, view and photometry from the header columns."""
import importlib.resources

import yaml

from .utils import categorize_column_regex

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
