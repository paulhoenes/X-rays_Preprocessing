"""Everything that touches the pixel data."""
import os

import numpy as np
import pydicom


def check_dicom_metadata(ds, row):
    """
    Standardizes tags for the training dataset.
    """
    ds.BodyPartExamined = row["bodypart_new"]
    ds.ViewPosition = row["view_position_new"]
    ds.Laterality = row["laterality_new"]
    
    # Store the filename inside the DICOM for easy viewing later
    ds.ReferringPhysicianName = row['filename_new_dupl']

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
    """
    Reads a DICOM, crops it to the Left or Right half, 
    updates metadata, and saves to the destination.
    """
    
    # Work from a local copy so the caller's row is never mutated (Bug 4 fix)
    row = row.copy()
    ds = pydicom.dcmread(src_path)

    # fix invertion
    if row['photometric_interpretation_new'] == 'MOne':
        ds = invert_monochrome(ds)
        row['photometric_interpretation_new'] = 'MTwo'        

    pixel_data = ds.pixel_array
    _, width = pixel_data.shape
    mid = width // 2

    cropped_pixels = pixel_data[:, mid:] if side == 'R' else pixel_data[:, :mid]
        
    # Update DICOM header metadata
    ds.Rows, ds.Columns = cropped_pixels.shape
    ds.PixelData = cropped_pixels.tobytes()
    #ds.Laterality = side

    # fix side
    if side == 'R':
        ds = mirror_right_to_left(ds)
    
    new_filename = (
        f"{row['pat_id']}_{row['study_date']}_{row['bodypart_new']}_"
        f"{side}_{row['view_position_new']}_{row['photometric_interpretation_new']}_"
        f"{row['dup_suffix']}_split"
    )
    
    return ds, new_filename
