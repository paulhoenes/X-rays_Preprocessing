"""The processing steps: read headers, categorize, select, write.

What gets *decided* is decided in rules.py -- here is only the order.
"""
import datetime
import os
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pydicom
import yaml

from .header import extract_metadata
from .pixels import (check_dicom_metadata, detect_bilateral,
                     invert_monochrome, mirror_right_to_left, split_dicom)
from .rules import categorize, load_rules, rebuild_filename, select
from .utils import get_unique_metadata, setup_logger

CONFIG = Path(__file__).parent / "config" / "rules.yaml"


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def run(input_dir, output_dir, bodypart="H", view="dp"):
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
    # Flatten directory structure, fix tags, mirror R→L, split B images.

    processed_dir.mkdir(parents=True, exist_ok=True)

    standalone_df = step3_df[step3_df['laterality_new'].isin(['L', 'R'])]
    bilateral_df  = step3_df[step3_df['laterality_new'] == 'B']
    other_df      = step3_df[~step3_df['laterality_new'].isin(['L', 'R', 'B'])]
    ordered_df    = pd.concat([standalone_df, bilateral_df, other_df], ignore_index=False)
 
    # Tracks which sides have been successfully written for each (pat_id, study_date).
    confirmed_sides: defaultdict[tuple, set] = defaultdict(set)
 
    logger.info(f"Processing {len(step3_df)} files for structure flattening ...")

    step4_rows = []
    
    for _, row in step3_df.iterrows():
        old_path = Path(row['filepathname_old'])
        new_filename = f"{row['filename_new_dupl']}.dcm"

        if not old_path.exists():
            logger.warning(f"File not found, skipping: {old_path}")
            continue

        try:

             # CASE 1: The image contains BOTH hands -> Only produce the sides not yet confirmed for this patient/date.
            if row['laterality_new'] == 'B':

                key          = (row['pat_id'], row['study_date'])
                sides_needed = {'L', 'R'} - confirmed_sides[key]

                logger.info(f"Processing {new_filename}; splitting into 2 images ...")

                if not sides_needed:
                    logger.info(
                        f"Skipping B-split for {new_filename}: both sides already "
                        f"confirmed for patient {row['pat_id']} on {row['study_date']}"
                    )
                    continue
 
                logger.info(
                    f"Processing {new_filename}; extracting side(s) {sides_needed} ..."
                )

                for side in sorted(sides_needed):  
    
                    ds, name = split_dicom(old_path, row.copy(), side)
 
                    new_row = row.copy()
                    new_row['laterality_new'] = side
                    new_row['IsMirrored']     = (side == 'R')
 
                    if row['photometric_interpretation_new'] == 'MOne':
                        new_row['photometric_interpretation_new'] = 'MTwo'
 
                    new_row['filename_new_dupl'] = name
 
                    ds = check_dicom_metadata(ds, new_row)
                    ds.save_as(str(processed_dir / f"{name}.dcm"))
                    step4_rows.append(new_row)
 
                    confirmed_sides[key].add(side)

            else: 

                # CASE 2: No modifications are needed (fix only invertion and side if needed)
                logger.info(f"Processing {new_filename}; placing file into correct folder ...")
 
                ds  = pydicom.dcmread(old_path)
                row = row.copy()  # isolate all mutations from the source DataFrame
 
                if row['photometric_interpretation_new'] == 'MOne':
                    ds = invert_monochrome(ds)
                    row['photometric_interpretation_new'] = 'MTwo'
                    row['filename_new_dupl'] = rebuild_filename(row)
                    new_filename = f"{row['filename_new_dupl']}.dcm"
 
                if row['laterality_new'] == 'R':
                    ds = mirror_right_to_left(ds)
                    row['IsMirrored'] = True
                else:
                    row['IsMirrored'] = False
 
                ds = check_dicom_metadata(ds, row)
                ds.save_as(str(processed_dir / new_filename))
                step4_rows.append(row)
 
                if row['laterality_new'] in ('L', 'R'):
                    confirmed_sides[(row['pat_id'], row['study_date'])].add(row['laterality_new'])
                

        except Exception as e:
            print(f"Error processing {old_path.name}: {e}")

    step4_df = pd.DataFrame(step4_rows)
    step4_df.to_csv(os.path.join(output_folder, "csvs/step4_metadata_df.csv"), index=False, errors='replace')
    
    logger.info(f"Step 4 done!; Time: {datetime.datetime.now()}")

    # Step 4 - skip; creates redundant copie of data by simply sorting them into corresponding categories
    # Step 5 - skip; look for duplicates & missing pairs
    # Step 6 - skip; does some comments based on manually checked images + fixes nans in file namings
    # Step 7 - partially skip; prepares comments for images modifications + fix rotations & splittings
    # Step 8 - skip; copy "images of interest" to separate folder
    # Step 9 - skip; compares if both sides are present
    # Step 10 - skip;
    # Step 11 - skip;
    # Step 12 - fix metadata tags;
    # Step 13a - partially skip; mirroring bodyparts if another part is not present
    # Step 13b - invertion to the same Photometric Interpretation
