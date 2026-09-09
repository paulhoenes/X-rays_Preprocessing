import logging
import os
import sys
import io
from datetime import datetime
from typing import Dict
 
import numpy as np
import pandas as pd
import pydicom
import SimpleITK as sitk
 
# Reconfigure stdout/stderr to replace characters that can't be encoded
#sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
#sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

###### Step 1

def setup_logger(output_folder):

    """Sets up a logger that writes to both the console and a file."""
    
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Generate a unique log filename based on the current time
    log_filename = datetime.now().strftime("pipeline_%Y%m%d_%H%M%S.log")
    log_path = os.path.join(output_folder, log_filename)

    #Create a custom logger
    logger = logging.getLogger("Preprocessing")
    logger.setLevel(logging.DEBUG)

    #Create handlers
    c_handler = logging.StreamHandler()  
    f_handler = logging.FileHandler(log_path)
    c_handler.setLevel(logging.INFO)       
    f_handler.setLevel(logging.DEBUG)     

    #Create formatters and add them to handlers
    log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    c_handler.setFormatter(log_format)
    f_handler.setFormatter(log_format)

    #Add handlers to the logger
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

    return logger


    
def get_unique_metadata(df, exclude_cols):
    """
    Extracts unique non-null values for specified columns and 
    returns a summary DataFrame.
    """
    
    # Filter columns we want to examine
    cols_to_process = [c for c in df.columns if c not in exclude_cols]
    
    # Create a dictionary of unique, non-null values for each column
    # .dropna().unique() is significantly faster than list(dict.fromkeys(...))
    unique_map = {
        col: pd.Series(df[col].dropna().unique()) 
        for col in cols_to_process
    }
    
    return pd.DataFrame(unique_map)

###### Step 2


# Function for checking if both left & right hands are present on the same date


    

###### Step 3
 


 
def rebuild_filename(row):

    return (
        f"{row['pat_id']}_{row['study_date']}_{row['bodypart_new']}_"
        f"{row['laterality_new']}_{row['view_position_new']}_"
        f"{row['photometric_interpretation_new']}_{row['dup_suffix']}"
    )