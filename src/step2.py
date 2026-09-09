# run python -W ignore::FutureWarning src/step2.py

from dicom_extremities_preprocessor.utils import setup_logger
 
import datetime
import pandas as pd
import os
import yaml
from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit
 
 
def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)


ROOT = Path.cwd()

config = load_config(ROOT / "dicom_extremities_preprocessor/resources/default.yaml")



# Get the info from config       
paths = config["paths"]
output_folder = paths["output_folder"]
dicom_server = paths["dicom_server"]
data_folder = paths["data_folder"]
logger = paths["logger"]
# metadata tags
tags = config["tags"]

logger = setup_logger(logger)
logger.info(f"Process started: {datetime.datetime.now()}......")


def main():

    logger.info("Reading step 4 output ...")
    df = pd.read_csv(os.path.join(output_folder, "csvs/step4_metadata_df.csv"))

    df = df.reset_index(drop=True)
    groups = df['pat_id'].values


    # --- 70 % train / 30 % temp split, grouped by patient ---
    gss_train = GroupShuffleSplit(n_splits=1, train_size=0.70, random_state=42)
    train_pos, temp_pos = next(gss_train.split(df, groups=groups))

    # --- Split the 30 % temp evenly: 15 % val / 15 % test ---
    temp_groups = groups[temp_pos]
    gss_val = GroupShuffleSplit(n_splits=1, train_size=0.50, random_state=42)
    val_rel_pos, test_rel_pos = next(gss_val.split(temp_pos, groups=temp_groups))
 
    val_pos  = temp_pos[val_rel_pos]
    test_pos = temp_pos[test_rel_pos]

    # add subset labels to the dataset
    df['dataset_split'] = 'unassigned'
    df.iloc[train_pos, df.columns.get_loc('dataset_split')] = 'train'
    df.iloc[val_pos,   df.columns.get_loc('dataset_split')] = 'val'
    df.iloc[test_pos,  df.columns.get_loc('dataset_split')] = 'test'

    counts = df['dataset_split'].value_counts().to_dict()
    logger.info(
        f"Split complete — train: {counts.get('train', 0)}, "
        f"val: {counts.get('val', 0)}, test: {counts.get('test', 0)}, "
        f"unassigned: {counts.get('unassigned', 0)}"
    )

    os.makedirs(os.path.join(output_folder, "csvs"), exist_ok=True)
    out_path = os.path.join(output_folder, "csvs/step5_split_df.csv")
    df.to_csv(out_path, index=False, errors='replace')
    logger.info(f"Saved split df to {out_path}. Done! Time: {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
