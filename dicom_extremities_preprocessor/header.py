"""Reading DICOM headers -- without the pixel data."""
from typing import Dict

import numpy as np
import SimpleITK as sitk


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
                val = reader.GetMetaData(tag).strip()
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
