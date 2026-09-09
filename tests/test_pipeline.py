"""A whole run over sample_data -- the files there cover every special case.

The sample files are not part of the repository (they are patient radiographs), so
these tests skip unless someone put their own DICOMs into demo/sample_data. The rules
themselves are covered without any data by test_rules.py.
"""
from pathlib import Path

import pandas as pd
import pydicom
import pytest

from dicom_extremities_preprocessor import cli, pipeline, pixels

SAMPLES = Path(__file__).resolve().parent.parent / "demo" / "sample_data"

pytestmark = pytest.mark.skipif(
    not SAMPLES.is_dir() or not any(SAMPLES.glob("*.dcm")),
    reason="no DICOMs in demo/sample_data -- see demo/README.md",
)


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("run")
    pipeline.run(SAMPLES, out, bodypart="H", views=("dp", "oblique"),
                 drop_unpaired=False)
    return out


def written(out):
    return sorted(p.name for p in (out / "dicoms").rglob("*.dcm"))


def test_every_written_file_has_a_real_side_and_is_monochrome2(result):
    names = written(result)
    assert names, "nothing written"
    for name in names:
        _, _, bodypart, side, _, photometric, _ = name.removesuffix(".dcm").split("_", 6)
        assert (bodypart, side, photometric[:4]) == ("H", side, "MTwo")
        assert side in ("L", "R")


def test_the_wrist_image_is_not_in_the_output(result):
    assert not [n for n in written(result) if n.startswith("752_")]


def test_monochrome1_is_inverted_and_renamed(result):
    ds = pydicom.dcmread(result / "dicoms" / "dp" / "1_20200202_H_L_dp_MTwo_0.dcm")
    assert ds.PhotometricInterpretation == "MONOCHROME2"

    source = pydicom.dcmread(SAMPLES / "raw_01.dcm")
    assert source.PhotometricInterpretation == "MONOCHROME1"
    assert ds.pixel_array.mean() != pytest.approx(source.pixel_array.mean())


def test_the_bilateral_image_becomes_two_halves(result):
    source = pydicom.dcmread(SAMPLES / "raw_03.dcm")
    assert pixels.shows_two_hands(source.pixel_array)

    half = pydicom.dcmread(result / "dicoms" / "oblique"
                           / "2_20200101_H_L_oblique_MTwo_0_split.dcm")
    assert half.Columns == source.Columns // 2
    assert half.Rows == source.Rows


def test_the_single_landscape_hand_is_left_whole(result):
    assert not pixels.shows_two_hands(pydicom.dcmread(SAMPLES / "raw_02.dcm").pixel_array)
    assert "2_20200101_H_R_oblique_MTwo_0.dcm" in written(result)


def test_pairs_hold_one_row_per_case(result):
    pairs = pd.read_csv(result / "csvs" / "pairs.csv")
    assert list(pairs.columns) == ["pat_id", "study_date", "laterality_new",
                                   "file_dp", "file_oblique", "status"]
    assert len(pairs) == len(pairs.drop_duplicates(
        ["pat_id", "study_date", "laterality_new"]))
    complete = pairs[pairs["status"] == "complete"]
    assert complete[["file_dp", "file_oblique"]].notna().all(axis=None)


def test_the_source_folder_is_untouched(result):
    before = {p.name: p.stat().st_mtime for p in SAMPLES.glob("*.dcm")}
    pipeline.run(SAMPLES, result, bodypart="H", views=("dp",), drop_unpaired=False)
    assert {p.name: p.stat().st_mtime for p in SAMPLES.glob("*.dcm")} == before


def test_scan_categorizes_without_writing_anything(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    df = pipeline.scan(SAMPLES)

    assert len(df) == len(list(SAMPLES.glob("*.dcm")))
    for column in ("bodypart_new", "laterality_new", "view_position_new",
                   "filename_new"):
        assert column in df.columns
    assert not list(tmp_path.iterdir())


def test_scan_only_on_the_command_line_writes_no_image(tmp_path, capsys):
    cli.main(["--input", str(SAMPLES), "--output", str(tmp_path), "--scan-only"])

    assert "headers read" in capsys.readouterr().out
    assert (tmp_path / "csvs" / "step2_categories.csv").is_file()
    assert not (tmp_path / "dicoms").exists()


def test_a_second_run_writes_nothing_new(result):
    stamps = {p: p.stat().st_mtime_ns for p in (result / "dicoms").rglob("*.dcm")}
    pipeline.run(SAMPLES, result, bodypart="H", views=("dp", "oblique"),
                 drop_unpaired=False)
    assert {p: p.stat().st_mtime_ns for p in (result / "dicoms").rglob("*.dcm")} == stamps
