# coding: utf-8
"""Exercise the FISM2 rebinning + namelist writing cells of input_file.ipynb
with synthetic indices (bypassing the network OMNI fetches), to verify the
file-writing logic produces valid TIEGCM-shape outputs."""
from pathlib import Path
import nbformat as nbf
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

# Run cell 2 (imports) and 8 (FISM2 rebin) and 10 (namelist) only.
# Inject synthetic NAMELIST_INDICES (the values F10.7 etc. that come from
# the network OMNI cell).
ns = {}
nb = nbf.read(ROOT / "input_file.ipynb", as_version=4)
exec(nb.cells[2].source, ns)  # imports & config

# Synthetic stand-ins for the OMNI-derived scalars
ns['NAMELIST_INDICES'] = dict(F107=178.0, F107A=160.0, POWER=37.5, CTPOTEN=66.0, KP=4.0)

# FISM2 rebin cell
exec(nb.cells[8].source, ns)
# Namelist generation cell
exec(nb.cells[10].source, ns)
# Validation cell (skip the IMF read-back since we did not run cell 4)
import xarray as xr
see = xr.open_dataset(ns['SEE_FILE'])
print("\nSEE dataset:")
print(see)
print("\nFinite SP_FLUX values:",
      int(np.isfinite(see['SP_FLUX'].values).sum()), "/", see['SP_FLUX'].size)
print("Zero rows (where flux=0 across day):",
      int((see['SP_FLUX'].values.max(axis=(1,2)) == 0).sum()))
