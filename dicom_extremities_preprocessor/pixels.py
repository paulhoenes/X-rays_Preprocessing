"""Everything that touches the pixel data: steps 3b and 4.

The counterpart to header.py, which never reads a pixel. Every change happens
on a copy in memory -- the source file is never written to, and the source
folder may be mounted read-only.
"""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

from .rules import rebuild_filename


def check_dicom_metadata(ds, row):
    """Write the derived categories back into the header."""
    ds.BodyPartExamined = row["bodypart_new"]
    ds.ViewPosition = row["view_position_new"]
    ds.Laterality = row["laterality_new"]
    ds.ReferringPhysicianName = row["filename_new_dupl"]
    return ds


def invert_monochrome(ds):
    """
    Inverts the pixel array of a DICOM object to convert MONOCHROME1 to MONOCHROME2.
    Does NOT save the file; returns the modified dataset object.
    """
    
    pixel_array = ds.pixel_array
    max_val = (2 ** ds.BitsStored) - 1
    inverted_pixels = max_val - pixel_array
    ds.PixelData = inverted_pixels.tobytes()
    ds.PhotometricInterpretation = "MONOCHROME2"
    return ds


def mirror_right_to_left(ds):
    """
    Horizontally flips a DICOM image and updates metadata.
    Use this for all Right hands (Train, Val, and Test) so they 
    anatomically match the orientation of Left hands.
    """

    mirrored_pixels = np.flip(ds.pixel_array, axis=1)
    ds.PixelData = mirrored_pixels.tobytes()
    
    return ds


def split_dicom(src_path, row, side):
    """Crop a bilateral image down to one half.

    The right half is mirrored afterwards, so it lies like a left hand.
    """
    ds = _decompress(pydicom.dcmread(src_path))
    if row["photometric_interpretation_new"] == "MOne":
        ds = invert_monochrome(ds)

    pixel = ds.pixel_array
    middle = pixel.shape[1] // 2
    half = pixel[:, middle:] if side == "R" else pixel[:, :middle]

    ds.Rows, ds.Columns = half.shape
    ds.PixelData = half.tobytes()
    return mirror_right_to_left(ds) if side == "R" else ds


def _decompress(ds):
    """Unpack compressed pixels before they are changed.

    If ds.PixelData is set anew without adjusting the transfer syntax, the
    result is a file that claims to be compressed but holds raw bytes --
    unreadable. Only affects devices that store compressed.
    """
    try:
        if ds.file_meta.TransferSyntaxUID.is_compressed:
            ds.decompress()
    except (AttributeError, KeyError):
        pass
    return ds


def shows_two_hands(pixel, min_gap: float = 0.04, min_brightness: float = 0.35,
                    min_column_fill: float = 0.06,
                    min_block_width: float = 0.12) -> bool:
    """Do two hands lie on this image, separated by a gap?

    The share of bright pixels is averaged over the columns, which gives a
    profile over the image width. A single hand leaves one connected block in
    that profile, two hands leave two blocks with a dark gap between them.

    The thresholds work on three levels and are coarse on purpose -- all that
    matters is telling one block of tissue from two:

        min_brightness    pixel    is this pixel tissue?
        min_column_fill   column   does this column hold enough tissue?
        min_block_width   block    is this block wide enough to be a hand?

    The defaults are the values from ``rules.yaml``; why the check is needed
    and when it runs is written there under ``bilateral``.

    Expects MONOCHROME2 (bone bright). Downscaling is done by stride -- enough
    for a column statistic and much faster on 2000x1700 px.
    """
    a = pixel.astype(np.float32)
    step = max(1, int(np.ceil(max(a.shape) / 400)))
    a = a[::step, ::step]

    lo, hi = np.percentile(a, [2, 98])
    if hi <= lo:                          # uniform image, nothing to see
        return False
    a = np.clip((a - lo) / (hi - lo), 0, 1)

    # The threshold grows with the image: on images with a bright background a
    # fixed value is not enough.
    share = (a > max(min_brightness, float(np.percentile(a, 60)))).mean(axis=0)
    width = len(share)
    window = max(3, width // 40)
    smoothed = np.convolve(share, np.ones(window) / window, mode="same")

    blocks, start = [], None
    for i, occupied in enumerate(smoothed > min_column_fill):
        if occupied and start is None:
            start = i
        elif not occupied and start is not None:
            blocks.append((start, i))
            start = None
    if start is not None:
        blocks.append((start, width))

    # Narrow blocks are labeling markers and the like, narrow gaps are gaps
    # between fingers -- neither may count as a second hand.
    wide = [b for b in blocks if (b[1] - b[0]) / width > min_block_width]
    merged: list[tuple[int, int]] = []
    for b in wide:
        if merged and (b[0] - merged[-1][1]) / width < min_gap:
            merged[-1] = (merged[-1][0], b[1])
        else:
            merged.append(b)
    return len(merged) >= 2


def detect_bilateral(sel, rules, log) -> pd.DataFrame:
    """Set bilateral images wrongly listed as a single hand to "B".

    Runs between selection and writing: only then does ``write_processed``
    split them like any other bilateral image. Pixels are read for the few
    landscape candidates only -- 55 of 8,032 images in this cohort.
    """
    cfg = rules.get("bilateral") or {}
    min_ratio = float(cfg.get("min_aspect_ratio", 1.0))
    profile = dict(
        min_gap=float(cfg.get("min_gap", 0.04)),
        min_brightness=float(cfg.get("min_brightness", 0.35)),
        min_column_fill=float(cfg.get("min_column_fill", 0.06)),
        min_block_width=float(cfg.get("min_block_width", 0.12)))

    sel = sel.copy()
    ratio = (pd.to_numeric(sel["columns"], errors="coerce")
             / pd.to_numeric(sel["rows"], errors="coerce"))
    candidates = sel[(ratio > min_ratio)
                     & sel["laterality_new"].isin(["L", "R"])]
    if candidates.empty:
        return sel

    hits = []
    for i, row in candidates.iterrows():
        try:
            pixel = pydicom.dcmread(row["filepathname_old"]).pixel_array
            if row["photometric_interpretation_new"] == "MOne":
                pixel = pixel.max() - pixel
            if shows_two_hands(pixel, **profile):
                hits.append(i)
        except Exception as e:
            log.warning(f"two-hand check failed for "
                        f"{row['filename_old']}: {type(e).__name__}: {e}")

    log.info(f"  {len(candidates)} landscape images checked, "
             f"{len(hits)} show two hands and get split")
    if hits:
        sel.loc[hits, "laterality_new"] = "B"
        sel.loc[hits, "filename_new_dupl"] = (
            sel.loc[hits].apply(rebuild_filename, axis=1))
    return sel


def write_processed(sel, output_dicoms, log, overwrite=False) -> pd.DataFrame:
    """Standardize the pixels and store them flat under a telling name.

    MONOCHROME1 is inverted, right hands are mirrored, bilateral images are
    split in the middle. The source is read, the in-memory copy is changed --
    the source file is never touched.

    The run is idempotent: existing target files are skipped without reading
    the pixels at all.
    """
    output_dicoms = Path(output_dicoms)
    output_dicoms.mkdir(parents=True, exist_ok=True)

    # Bilateral images last: for them only the sides are produced that are not
    # already there from a single image.
    single = sel[sel["laterality_new"].isin(["L", "R"])]
    bilateral = sel[sel["laterality_new"] == "B"]
    rest = sel[~sel["laterality_new"].isin(["L", "R", "B"])]
    ordered = pd.concat([single, bilateral, rest])

    done: defaultdict[tuple, set] = defaultdict(set)
    rows, written, skipped, errors = [], 0, 0, 0

    def store(row, dest, load_pixels):
        """Record the row and write it -- ``load_pixels`` only if needed."""
        nonlocal written, skipped
        row["filename_written"] = dest.name
        rows.append(row)
        if dest.exists() and not overwrite:
            skipped += 1
            return
        check_dicom_metadata(load_pixels(), row).save_as(str(dest))
        written += 1

    for n, (_, row) in enumerate(ordered.iterrows(), 1):
        src = Path(row["filepathname_old"])
        if not src.exists():
            log.warning(f"not found, skipped: {src}")
            errors += 1
            continue

        try:
            if row["laterality_new"] == "B":
                key = (row["pat_id"], row["study_date"])
                missing = {"L", "R"} - done[key]
                for side in sorted(missing):
                    new_row = row.copy()
                    new_row["laterality_new"] = side
                    new_row["IsMirrored"] = (side == "R")
                    if new_row["photometric_interpretation_new"] == "MOne":
                        new_row["photometric_interpretation_new"] = "MTwo"
                    new_row["filename_new_dupl"] = f"{rebuild_filename(new_row)}_split"
                    store(new_row,
                          output_dicoms / f"{new_row['filename_new_dupl']}.dcm",
                          lambda s=side: split_dicom(src, row, s))
                    done[key].add(side)
            else:
                row = row.copy()
                row["IsMirrored"] = (row["laterality_new"] == "R")
                # Determine the target name up front: MONOCHROME1 becomes MTwo,
                # and that is part of the file name. Only this way can an
                # existing result be recognized without reading the pixels.
                if row["photometric_interpretation_new"] == "MOne":
                    row["photometric_interpretation_new"] = "MTwo"
                    row["filename_new_dupl"] = rebuild_filename(row)
                    invert = True
                else:
                    invert = False
                dest = output_dicoms / f"{row['filename_new_dupl']}.dcm"

                def load_pixels(src=src, invert=invert,
                                mirror=row["IsMirrored"]):
                    ds = _decompress(pydicom.dcmread(src))
                    if invert:
                        ds = invert_monochrome(ds)
                    return mirror_right_to_left(ds) if mirror else ds

                store(row, dest, load_pixels)
                if row["laterality_new"] in ("L", "R"):
                    done[(row["pat_id"], row["study_date"])].add(
                        row["laterality_new"])

        except Exception as e:      # one broken file must not end the run
            log.warning(f"error on {src.name}: {type(e).__name__}: {e}")
            errors += 1

        if n % 200 == 0:
            log.info(f"  {n}/{len(ordered)} processed")

    log.info(f"written {written}, skipped {skipped} "
             f"(already there), errors {errors}")
    return pd.DataFrame(rows)
