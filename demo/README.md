# demo

**None of this is needed to use the package.** To process your own data, `pip install`
the repository and point the command line at your folder -- see the main
[README](../README.md). This folder can be deleted without touching anything.

[`demo.ipynb`](demo.ipynb) walks through the package one step at a time: reading
headers, deriving the categories, detecting a bilateral image, running the whole chain
and looking at what was written.

## It needs data you bring yourself

The notebook expects raw DICOM files in `sample_data/`. **They are not part of this
repository** -- the ones it was written against are patient radiographs and stay where
they belong.

Put your own extremity DICOMs there:

```
demo/sample_data/
├── raw_01.dcm
├── raw_02.dcm
└── ...
```

Anything the radiology archive exports will do. The notebook is most instructive if the
files cover a few special cases -- a MONOCHROME1 image, a right hand, a film showing
both hands at once, and something that is not a hand at all.

## Running it

```bash
pip install -e ".[plot]"      # from the repository root
jupyter lab demo/demo.ipynb
```

It writes into `demo/output/` and reads nothing outside this folder.

Outputs are stripped before every commit (`nbstripout`, see
[`.pre-commit-config.yaml`](../.pre-commit-config.yaml)), so the notebook in the
repository holds code only -- run it to see the images.
