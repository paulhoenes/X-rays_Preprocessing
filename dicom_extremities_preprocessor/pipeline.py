"""The processing steps: read headers, categorize, select, write.

What gets *decided* is decided in rules.py -- here is only the order.
"""
import datetime
import os
from pathlib import Path

import pandas as pd
import yaml

from .header import extract_metadata
from .pixels import detect_bilateral, write_processed
from .rules import categorize, load_rules, rebuild_filename, select
from .utils import get_unique_metadata, setup_logger

CONFIG = Path(__file__).parent / "config" / "rules.yaml"


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def run(input_dir, output_dir, bodypart="H", view="dp", overwrite=False):
    """Read input_dir, write the processed DICOMs and tables below output_dir."""
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    tags = load_config(CONFIG)["tags"]

    output_folder = output_dir
    data_folder = input_dir
    processed_dir = output_dir / "dicoms"

    logger = setup_logger(output_dir)
    logger.info(f"Process started: {datetime.datetime.now()}......")

    ###########################
    ##         Step 1        ##
    ###########################
    # Read all DICOM files and extract metadata tags.
    # Create a list of unique metadata values for future category mappings.

    logger.info("Starting DICOM file extraction.......")

    # Gather files


    all_files = [os.path.join(dp, f) 
                 for dp, _, filenames in os.walk(data_folder) 
                 for f in filenames if not f.startswith('.')]
    
    
    logger.info(f"Processing {len(all_files)} files")
    
    results = [meta for f in all_files if (meta := extract_metadata(f, tags))]
    
    df = pd.DataFrame(results)



    n_unique = df["filename_old"].nunique()
    n_nonnull = df["filename_old"].notna().sum()
    if n_unique == n_nonnull:
        logger.info(f"Created df of shape {df.shape}; all files are unique")
    else:
        logger.info(f"Created df of shape {df.shape}; not all files are unique")


    # Save metadata
    os.makedirs(os.path.join(output_folder, "csvs"), exist_ok=True)
    df.to_csv(os.path.join(output_folder, "csvs/step1_metadata_df.csv"), index=False, errors='replace')
    logger.info("Saved step 1 metadata df")

    # Calculate unique combinatinations pat_id & study_date

    im_per_iddate = (df.groupby(['pat_id', 'study_date'])
                       .size()
                       .reset_index()
                       .rename(columns={0: 'count'}))
    im_per_iddate.to_csv(os.path.join(output_folder, "csvs/step1_im_per_iddate.csv"), index=False, errors='replace')
    logger.info("Saved df with unique patient visits and days")

    exclude = ["filepath_old", "filename_old", "filepathname_old", 
            "columns", "rows", "pat_id", "study_date"]

    pat_dict_unique_df = get_unique_metadata(df, exclude)

    # Save unique metadata
    pat_dict_unique_df.to_csv(os.path.join(output_folder, "csvs/step1_metadata_unique_df.csv"), index=False, errors='replace')

    logger.info(f"Saved df with unique metadata. Step 1 done! Time: {datetime.datetime.now()}")

    ###########################
    ##         Step 2        ##
    ###########################
    # Use metadata fields to standardise body part, laterality, view position,
    # and photometric interpretation. Generate new filenames.

    # 1. Categorization
    step2_df = df.copy()


    step2_df = categorize(step2_df, load_rules(), logger)

    step2_df.to_csv(os.path.join(output_folder, "csvs/step2_metadata_df.csv"), index=False, errors='replace')
    logger.info(f"Finished new filename creation. Step 2 done! Time: {datetime.datetime.now()}")
    
      
    ###########################
    ##         Step 3        ##
    ###########################
    # Keep only hands DP images, detect duplicates, and add a numeric suffix.

    step3_df = select(step2_df, logger, bodypart=bodypart, view=view)
    step3_df = detect_bilateral(step3_df, load_rules(), logger)

    # Save updated file
    step3_df.to_csv(os.path.join(output_folder, "csvs/step3_metadata_df.csv"), index=False, errors='replace')

    logger.info(f"Saved step 3 df ({len(step3_df)} rows). Step 3 done! Time: {datetime.datetime.now()}")

    ###########################
    ##         Step 4        ##
    ###########################
    # Standardise the pixels and write them out.

    written = write_processed(step3_df, processed_dir, logger, overwrite=overwrite)
    written.to_csv(os.path.join(output_folder, "csvs/step4_written.csv"),
                   index=False, errors="replace")
    logger.info(f"Step 4 done!; Time: {datetime.datetime.now()}")
    return processed_dir
