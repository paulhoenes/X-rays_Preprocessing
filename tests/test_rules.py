"""The decisions in rules.py -- no files involved, only tables."""
import logging

import pandas as pd
import pytest

from dicom_extremities_preprocessor import rules

log = logging.getLogger("test")


def header(**overrides):
    """One header row, with the fields categorize() expects."""
    row = {"pat_id": "1", "study_date": "20200303", "series_description": "",
           "study_description": "", "body_part_examined": "", "laterality": "",
           "view_position": "", "photometric_interpretation": "MONOCHROME2"}
    row.update(overrides)
    return row


def categorize(*rows):
    return rules.categorize(pd.DataFrame(rows), rules.load_rules(), log)


@pytest.mark.parametrize("text, expected", [
    ("T106 Hand schräg links", "t106 hand schraeg links"),
    ("Unterarm / Handgelenk pa L", "unterarm / handgelenk pa l"),
    ("Fuß  d.p.", "fuss d p"),
    (None, ""),
])
def test_normalize_text(text, expected):
    assert rules.normalize_text(text) == expected


def test_free_text_beats_tag_for_bodypart():
    # BodyPartExamined is often a station default -- here it claims a hand
    df = categorize(header(body_part_examined="HAND", series_description="Knie li"))
    assert df["bodypart_new"][0] == "O"


def test_tag_is_used_when_the_text_says_nothing():
    df = categorize(header(body_part_examined="HAND"))
    assert df["bodypart_new"][0] == "H"


def test_lat_is_oblique_for_hands_but_not_for_feet():
    df = categorize(header(series_description="Hand lat re"),
                    header(series_description="Fuss lat re"))
    assert list(df["view_position_new"]) == ["oblique", "lat"]


def test_oblique_pattern_wins_over_lat():
    # the label order in rules.yaml is the priority
    df = categorize(header(series_description="Hand schraeg lat li"))
    assert df["view_position_new"][0] == "oblique"


def test_wrist_and_finger_images_leave_the_hand_category():
    df = categorize(header(body_part_examined="HAND", series_description="Handgelenk dp L"),
                    header(body_part_examined="HAND", series_description="Daumen li"),
                    header(body_part_examined="HAND", series_description="Hand dp li"))
    assert list(df["bodypart_new"]) == ["O", "O", "H"]


def test_side_falls_back_from_tag_to_view_position_to_text():
    df = categorize(header(laterality="R", view_position="LLO", series_description="Hand li"),
                    header(view_position="LLO", series_description="Hand dp"),
                    header(series_description="Hand dp rechts"))
    assert list(df["laterality_new"]) == ["R", "L", "R"]


def test_view_ignores_the_study_description():
    # "Hand dp Zitherstellung" names the whole visit, both views were taken --
    # the dp image of such a visit must not turn into an oblique one
    df = categorize(header(series_description="Hand dp li",
                           study_description="Hand dp Zitherstellung"))
    assert df["view_position_new"][0] == "dp"


def test_select_drops_images_without_a_side():
    df = categorize(header(series_description="Hand dp li"),
                    header(series_description="Hand dp"))
    assert len(rules.select(df, log, bodypart="H", view="dp")) == 1


def test_select_numbers_duplicates():
    same = dict(series_description="Hand dp li")
    sel = rules.select(categorize(header(**same), header(**same)), log,
                       bodypart="H", view="dp")
    assert list(sel["filename_new_dupl"]) == ["1_20200303_H_L_dp_MTwo_0",
                                              "1_20200303_H_L_dp_MTwo_1"]


def test_rebuild_filename_follows_a_changed_category():
    sel = rules.select(categorize(header(series_description="Hand dp re")), log,
                       bodypart="H", view="dp")
    row = sel.iloc[0].copy()
    row["laterality_new"] = "L"
    assert rules.rebuild_filename(row) == "1_20200303_H_L_dp_MTwo_0"
