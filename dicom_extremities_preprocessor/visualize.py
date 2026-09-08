"""Image grids for checking a selection by eye.

Not used by the pipeline -- this is a viewing aid for notebooks and quality
control. Needs matplotlib, which is an optional dependency, so this module is
not imported by ``__init__.py``::

    from dicom_extremities_preprocessor import visualize

The column names default to those the pipeline produces
(``filepathname_old`` before writing); pass ``file_path_column`` for a table
that names the files differently.
"""



from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pydicom


def load_grayscale(file_path) -> np.ndarray:
    """Pixels of one file as float, MONOCHROME1 already inverted."""
    ds = pydicom.dcmread(str(file_path))
    img = ds.pixel_array.astype(np.float32)
    if getattr(ds, "PhotometricInterpretation", None) == "MONOCHROME1":
        img = img.max() - img
    return img


def _label(row: pd.Series, cols) -> str:
    return "\n".join("-" if pd.isna(row[c]) else str(row[c])
                     for c in cols if c in row.index)


def visualize_samples(df: pd.DataFrame, info_cols=None, ncols: int = 8,
                      file_path_column: str = "filepathname_old",
                      label_below: bool = True):
    """Plot the images of ``df`` in a grid, labelled with metadata.

    ``df`` holds one row per image -- usually a sample, not the whole table
    (``df.sample(32)``). ``info_cols`` names the columns written under each
    image. A file that cannot be read leaves a black tile with the error on
    it, so a broken file does not end the plot.

    Returns the figure and the axes array.
    """
    if df.empty:
        raise ValueError("df is empty")

    nrows = math.ceil(len(df) / ncols)
    fig, axes = plt.subplots(nrows, ncols, squeeze=False,
                             figsize=(2.2 * ncols, 2.6 * nrows))

    for i, (_, row) in enumerate(df.iterrows()):
        ax = axes[divmod(i, ncols)]
        try:
            ax.imshow(load_grayscale(row[file_path_column]),
                      cmap="gray", aspect="equal")
        except Exception as exc:
            ax.imshow(np.zeros((64, 64)), cmap="gray", aspect="equal")
            ax.text(0.5, 0.5, f"not readable\n{exc}", transform=ax.transAxes,
                    ha="center", va="center", fontsize=7, color="red")

        if info_cols:
            text = _label(row, info_cols)
            if label_below:
                ax.text(0.5, -0.08, text, transform=ax.transAxes,
                        ha="center", va="top", fontsize=7)
            else:
                ax.set_title(text, fontsize=7, pad=4)
        ax.set_xticks([])
        ax.set_yticks([])

    for j in range(len(df), nrows * ncols):
        axes[divmod(j, ncols)].axis("off")

    if label_below:
        fig.subplots_adjust(bottom=0.12, hspace=0.45, wspace=0.15)
    else:
        fig.tight_layout()
    return fig, axes
