"""Reading DICOM headers -- without the pixel data."""
from typing import Dict

import numpy as np
import SimpleITK as sitk


def fix_umlauts(value: str) -> str:
    """Repair umlauts that SimpleITK returns as replacement characters.

    SimpleITK passes the tag content through as raw bytes; Python decodes them
    as UTF-8 with surrogateescape, so the Latin-1 byte 0xE4 ("ae") becomes
    U+DCE4 instead of "ä" -- a character no text rule matches and that cannot
    be written to a CSV as UTF-8 either.

    "T106 Hand schräg rechts" arrived as "T106 Hand schr\\udce4g rechts" and
    matched neither the pattern for the oblique view nor the one for the side.
    """
    if not any("\udc80" <= c <= "\udcff" for c in value):
        return value
    raw = value.encode("utf-8", "surrogateescape")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def extract_metadata(file_path: str, tag_map: Dict[str, str]) -> Dict:
    """Extracts DICOM tags for a single file."""
    try:
        reader = sitk.ImageFileReader()
        reader.SetFileName(file_path)
        reader.LoadPrivateTagsOn()
        reader.ReadImageInformation()
        
        # Build dictionary for this specific file
        entry = {}
        for label, tag in tag_map.items():
            if reader.HasMetaDataKey(tag):
                val = fix_umlauts(reader.GetMetaData(tag)).strip()
                entry[label] = val if val != "" else "emptystr"
            else:
                entry[label] = np.nan
        
        # Add file info
        entry['filename_old'] = os.path.basename(file_path)
        entry['filepathname_old'] = file_path
        return entry
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None
