"""Supporting cast: things the pipeline uses that are not steps of it."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import pandas as pd


def setup_logger(output_folder) -> logging.Logger:
    """Log to the console (INFO) and to a file in the output folder (DEBUG)."""
    os.makedirs(output_folder, exist_ok=True)
    path = os.path.join(output_folder,
                        datetime.now().strftime("pipeline_%Y%m%d_%H%M%S.log"))

    log = logging.getLogger("Preprocessing")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()          # otherwise doubled on repeated run() calls
    log.propagate = False         # and doubled again where the root logger is set up
    for handler, level in ((logging.StreamHandler(), logging.INFO),
                           (logging.FileHandler(path), logging.DEBUG)):
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        log.addHandler(handler)
    return log


def get_unique_metadata(df, exclude_cols) -> pd.DataFrame:
    """The unique values per column -- the basis for writing new text rules.

    Not part of the chain. Use it on a new cohort to see what the free text
    fields actually contain before adding patterns to ``rules.yaml``.
    """
    return pd.DataFrame({c: pd.Series(df[c].dropna().unique())
                         for c in df.columns if c not in exclude_cols})
