"""Step 1: read the DICOM headers -- without the pixel data.

Only the tags listed in ``config/rules.yaml`` under ``tags:`` are read, through
SimpleITK. On a large data set on a network drive that is the difference
between minutes and hours, because the pixels are almost the whole volume.

Nothing here decides anything. What the values mean is settled in ``rules.py``.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import SimpleITK as sitk


def fix_umlauts(value: str) -> str:
    """Repair umlauts that SimpleITK returns as replacement characters.

    SimpleITK passes the tag content through as raw bytes; Python decodes them
    as UTF-8 with ``surrogateescape``. The Latin-1 byte 0xE4 ("ae") becomes
    U+DCE4 instead of "ä" -- a character no text rule matches and that cannot
    be written to a CSV as UTF-8 either (a "?" ended up there).

    Concretely: "T106 Hand schräg rechts" arrived as
    "T106 Hand schr\\udce4g rechts", matched neither the pattern for the
    oblique view nor the one for the side -- 78 hand images were left without a
    view and without a side.

    So the bytes are turned back and decoded properly: UTF-8 first (ISO_IR
    192), else Latin-1 (ISO_IR 100, what the German devices deliver here).
    Text without replacement characters is left alone.
    """
    if not any("\udc80" <= c <= "\udcff" for c in value):
        return value
    raw = value.encode("utf-8", "surrogateescape")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def extract_metadata(file_path: str, tag_map: dict) -> dict | None:
    """Read the configured tags of one file -- without the pixel data.

    Returns ``None`` if the file is not a readable DICOM.
    """
    try:
        reader = sitk.ImageFileReader()
        reader.SetFileName(file_path)
        reader.LoadPrivateTagsOn()
        reader.ReadImageInformation()
    except Exception:
        return None

    entry = {}
    for column, tag in tag_map.items():
        if not reader.HasMetaDataKey(tag):
            entry[column] = np.nan
            continue
        value = fix_umlauts(reader.GetMetaData(tag)).strip()
        entry[column] = value if value else "emptystr"

    entry["filename_old"] = os.path.basename(file_path)
    entry["filepathname_old"] = file_path
    return entry


def scan_metadata(input_dir, tags, log) -> pd.DataFrame:
    """Read the header of every file below ``input_dir``.

    Searches without a suffix filter, because raw data often carries no
    ``.dcm`` suffix, and serially with ``os.walk`` -- walking in parallel
    overwhelms sshfs and silently returns incomplete results.
    """
    files = [os.path.join(dp, f)
             for dp, _, names in os.walk(input_dir)
             for f in names if not f.startswith(".")]
    log.info(f"files found: {len(files)}")

    entries = [m for f in files if (m := extract_metadata(f, tags))]
    df = pd.DataFrame(entries)
    if df.empty:
        raise SystemExit(f"No readable DICOMs under {input_dir}")

    log.info(f"headers read: {len(df)} of {len(files)}")
    return df
