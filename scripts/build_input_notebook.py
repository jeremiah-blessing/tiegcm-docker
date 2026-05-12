# coding: utf-8
"""Build input_file.ipynb -- generator script for the TIEGCM X5.1 flare-run
input preparation notebook. Run once; leaves input_file.ipynb in repo root."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
OUT  = ROOT / "input_file.ipynb"

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {"name": "python3", "display_name": "Python 3 (.venv)"},
    "language_info": {"name": "python"},
}

def md(text):  nb.cells.append(nbf.v4.new_markdown_cell(text))
def code(src): nb.cells.append(nbf.v4.new_code_cell(src))

# ---------------------------------------------------------------------------
md(r"""# TIEGCM input preparation -- X5.1 flare run, 2025-11-11

Builds the three input files TIEGCM v3.0 needs for a Weimer + spectral-EUV run
over the X5.1 flare of **2025-11-11 02:00-16:00 UT** (flare peak 10:05 UT).

| File | Purpose | Built from |
|---|---|---|
| `data/imf_OMNI_20251111.nc`       | High-lat convection / Weimer-2005 driver | OMNI 1-min HRO via `pyspedas` |
| `data/see_FISM2_20251111.nc`      | Spectral solar irradiance (37 EUVAC bins) | local FISM2 60-s `data/FISM_60sec_2025315_v02_01.nc` |
| `data/tiegcm_flare_20251111.inp`  | Namelist that wires it all together      | written in last cell |

F10.7 and Kp come back as scalar values from `pyspedas.omni`; they go directly
into the namelist (no GPI file needed for a single-event run).

Run cells top-to-bottom. Network cells (OMNI fetch) take ~30 s each.""")

# ---------------------------------------------------------------------------
md("## 0. Imports and config")

code(r"""from pathlib import Path
import numpy as np
import xarray as xr
from datetime import datetime, timezone, timedelta

# Event constants
EVENT_DATE   = datetime(2025, 11, 11, tzinfo=timezone.utc)
DOY          = EVENT_DATE.timetuple().tm_yday          # 315
YEAR         = EVENT_DATE.year
RUN_START_UT = datetime(2025, 11, 11,  2, 0, tzinfo=timezone.utc)
RUN_STOP_UT  = datetime(2025, 11, 11, 16, 0, tzinfo=timezone.utc)

# Fetch a generous OMNI window so the model has interpolation buffer at both ends
OMNI_START = datetime(2025, 11, 10, 22, 0, tzinfo=timezone.utc)
OMNI_STOP  = datetime(2025, 11, 11, 18, 0, tzinfo=timezone.utc)

ROOT = Path.cwd()
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

FISM2_FILE  = DATA / "FISM_60sec_2025315_v02_01.nc"
IMF_FILE    = DATA / "imf_OMNI_20251111.nc"
SEE_FILE    = DATA / "see_FISM2_20251111.nc"
NAMELIST    = DATA / "tiegcm_flare_20251111.inp"

print(f"Event   : {EVENT_DATE:%Y-%m-%d}  (DOY={DOY})")
print(f"Window  : {RUN_START_UT:%H:%M} -> {RUN_STOP_UT:%H:%M} UT")
print(f"FISM2   : {FISM2_FILE}  exists={FISM2_FILE.exists()}")
""")

# ---------------------------------------------------------------------------
md(r"""## 1. OMNI 1-min IMF + solar wind  ->  `imf_OMNI_20251111.nc`

TIEGCM's `IMF_NCFILE` reader (`tiegcm/src/imf.F`) expects:

| netCDF var | type   | meaning |
|------------|--------|---------|
| `date`     | double | `yyyyddd.dayfrac` (e.g. 2025315.5 = 2025-11-11 12:00 UT) |
| `bx`, `by`, `bz` | double | IMF components in **GSM**, nT |
| `swvel`    | double | solar wind speed, km s-1 |
| `swden`    | double | solar wind number density, cm-3 |

The single dimension is `ndata` (number of records). Missing values are fatal
to the model -- we fill any gaps in OMNI with the nearest valid value and warn.""")

code(r"""import pyspedas
from pyspedas import get_data, del_data   # pyspedas 2.x merged pytplot here

del_data()  # clear any prior tplot vars
trange = [OMNI_START.strftime('%Y-%m-%d/%H:%M'),
          OMNI_STOP .strftime('%Y-%m-%d/%H:%M')]
print(f"Fetching OMNI 1-min HRO for {trange} ...")

vars_needed = ['BX_GSE', 'BY_GSM', 'BZ_GSM', 'flow_speed', 'proton_density']
pyspedas.projects.omni.data(trange=trange, datatype='1min', varnames=vars_needed,
                             time_clip=True, no_update=False)

t   = get_data('BX_GSE').times                       # POSIX seconds
bx  = get_data('BX_GSE').y                           # GSM X = GSE X
by  = get_data('BY_GSM').y
bz  = get_data('BZ_GSM').y
sv  = get_data('flow_speed').y
sd  = get_data('proton_density').y

def clean(a):
    a = np.asarray(a, dtype=float)
    mask = ~np.isfinite(a)
    if mask.all():
        raise RuntimeError("All-NaN column from OMNI -- check network / trange.")
    out = a.copy()
    last = np.nan
    for i in range(len(out)):
        if np.isfinite(out[i]):
            last = out[i]
        else:
            out[i] = last
    if not np.isfinite(out[0]):
        first_good = int(np.argmax(np.isfinite(a)))
        out[:first_good] = a[first_good]
    n_filled = int(mask.sum())
    if n_filled:
        print(f"  filled {n_filled} missing OMNI samples")
    return out

bx, by, bz, sv, sd = map(clean, (bx, by, bz, sv, sd))

# Build TIEGCM date = yyyyddd.dayfrac
dates = []
for ts in t:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    doy = dt.timetuple().tm_yday
    dayfrac = (dt.hour*3600 + dt.minute*60 + dt.second + dt.microsecond/1e6) / 86400.0
    dates.append(dt.year*1000.0 + doy + dayfrac)
dates = np.asarray(dates, dtype=np.float64)

ds_imf = xr.Dataset(
    data_vars=dict(
        date  = (('ndata',), dates,        {'long_name': 'yyyyddd.dayfrac UT'}),
        bx    = (('ndata',), bx.astype(np.float64),  {'units':'nT', 'long_name':'IMF Bx GSM'}),
        by    = (('ndata',), by.astype(np.float64),  {'units':'nT', 'long_name':'IMF By GSM'}),
        bz    = (('ndata',), bz.astype(np.float64),  {'units':'nT', 'long_name':'IMF Bz GSM'}),
        swvel = (('ndata',), sv.astype(np.float64),  {'units':'km/s'}),
        swden = (('ndata',), sd.astype(np.float64),  {'units':'cm-3'}),
    ),
    attrs=dict(
        source='OMNI 1-min HRO via pyspedas',
        event='X5.1 flare 2025-11-11',
        history=f'created {datetime.utcnow():%Y-%m-%d %H:%M} UT',
    ),
)
ds_imf.to_netcdf(IMF_FILE)
print(f"\nWrote {IMF_FILE}  ({len(dates)} records)")
print(f"  Bz range : {bz.min():+6.2f} .. {bz.max():+6.2f} nT")
print(f"  Vsw range: {sv.min():6.1f} .. {sv.max():6.1f} km/s")
""")

# ---------------------------------------------------------------------------
md(r"""## 2. F10.7 and Kp scalar values for the namelist

For a single-day event run we set scalar `F107`, `F107A`, `POWER`, `CTPOTEN`
in the namelist (no GPI file). F10.7 (daily and 81-day average) lives in the
**1-hour OMNI** product as `F10_INDEX`. Kp is `Kp_index` (stored x10).

Once `POTENTIAL_MODEL='WEIMER'` is set, TIEGCM uses the IMF file for
high-latitude convection and CTPOTEN/POWER are floors only. We still need to
supply them.""")

code(r"""del_data()
# Hourly OMNI: datatype='hourly' in pyspedas 2.x; F10_INDEX and KP are flagged
# as support data so we must pass get_ignore_data=True to actually load them.
# Hourly loader also rejects HH:MM in trange -- use date-only.
trange_hr = [OMNI_START.strftime('%Y-%m-%d'),
             OMNI_STOP .strftime('%Y-%m-%d')]
pyspedas.projects.omni.data(trange=trange_hr, datatype='hourly',
    time_clip=True, no_update=False, get_ignore_data=True)

f107_hr = get_data('F10_INDEX').y
kp_hr   = get_data('KP').y
# OMNI Kp is stored x10 (e.g. 47 means 4.7); guard if convention changes
kp_vals = kp_hr / (10.0 if np.nanmax(kp_hr) > 9.5 else 1.0)

F107  = float(np.nanmean(f107_hr))

# 81-day F10.7A: separate fetch covering +/-40 days
trange_81 = [(EVENT_DATE - timedelta(days=41)).strftime('%Y-%m-%d'),
             (EVENT_DATE + timedelta(days=41)).strftime('%Y-%m-%d')]
del_data()
pyspedas.projects.omni.data(trange=trange_81, datatype='hourly',
    time_clip=True, no_update=False, get_ignore_data=True)
F107A = float(np.nanmean(get_data('F10_INDEX').y))

KP      = float(np.nanmax(kp_vals))   # peak Kp during run
POWER   = 5.0 + 7.5 * KP              # rough fit (Zhang & Paxton 2008 family)
CTPOTEN = 29.0 + 11.0 * KP            # standard TIEGCM gpi.F formula

print(f"F107   (event-day mean) = {F107:7.2f} sfu")
print(f"F107A  (81-day mean)    = {F107A:7.2f} sfu")
print(f"Kp     (peak in window) = {KP:5.2f}")
print(f"POWER  (derived, GW)    = {POWER:6.2f}")
print(f"CTPOTEN(derived, kV)    = {CTPOTEN:6.2f}")

NAMELIST_INDICES = dict(F107=F107, F107A=F107A, POWER=POWER, CTPOTEN=CTPOTEN, KP=KP)
""")

# ---------------------------------------------------------------------------
md(r"""## 3. FISM2 60-s  ->  TIEGCM SEE 37-bin file  ->  `see_FISM2_20251111.nc`

TIEGCM v3.0 hard-codes a **37-bin EUVAC** wavelength scheme
(`tiegcm/src/qrj.F:476-514`); the SEE-file reader (`soldata.F`) shuts down if
`nwave != 37`. The bins are in **angstroms**, descending from 1750 A to 0.5 A:

- **Bin 12 (1215.67 A, zero-width)** is the Lyman-alpha line. We integrate
  FISM2 over a 1-nm window 121.0-122.0 nm.
- **Bin 11 (1200-1250 A)** is the continuum -- the Lyman-alpha line flux is
  subtracted so it is not double-counted with bin 12.
- **Bins 19-21 (913-975 A)**, **22-24 (798-913 A)**, **25-26 (650-798 A)**
  are EUVAC duplicate-range bins (line vs continuum splits with different
  per-species photoionization cross-sections internally). TIEGCM expects a
  flux value in each duplicate. For a first-pass FISM2 ingest we put **the
  total band flux divided equally** in each duplicate. For higher accuracy
  replace this with a Solomon & Qian (2005) line-resolved decomposition.
- **>1750 A** is outside TIEGCM photochemistry -- discarded.

Output schema follows `tiegcm/src/soldata.F:80-103` exactly.""")

code(r"""# TIEGCM 37-bin EUVAC wavelengths (qrj.F:499-514) -- units = Angstrom
WAVE1_A = np.array([1700.00, 1650.00, 1600.00, 1550.00, 1500.00,
                    1450.00, 1400.00, 1350.00, 1300.00, 1250.00,
                    1200.00, 1215.67, 1150.00, 1100.00, 1050.00,
                    1027.00,  987.00,  975.00,  913.00,  913.00,
                     913.00,  798.00,  798.00,  798.00,  650.00,
                     650.00,  540.00,  320.00,  290.00,  224.00,
                     155.00,   70.00,   32.00,   18.00,    8.00,
                       4.00,    0.50])
WAVE2_A = np.array([1750.00, 1700.00, 1650.00, 1600.00, 1550.00,
                    1500.00, 1450.00, 1400.00, 1350.00, 1300.00,
                    1250.00, 1215.67, 1200.00, 1150.00, 1100.00,
                    1050.00, 1027.00,  987.00,  975.00,  975.00,
                     975.00,  913.00,  913.00,  913.00,  798.00,
                     798.00,  650.00,  540.00,  320.00,  290.00,
                     224.00,  155.00,   70.00,   32.00,   18.00,
                       8.00,    4.00])
NWAVE = 37
assert WAVE1_A.size == WAVE2_A.size == NWAVE

fism = xr.open_dataset(FISM2_FILE)
wl_nm = fism['wavelength'].values.astype(np.float64)         # 1900 pts 0.05..190 nm
irr   = fism['irradiance'].values.astype(np.float64)         # (utc, wavelength) W/m2/nm
utc_s = fism['utc'].values.astype(np.float64)                # seconds-of-day, 60-s cadence
ndate = irr.shape[0]
print(f"FISM2 loaded: ndate={ndate}, nwave_native={wl_nm.size}")

# W/m^2/nm  ->  photons/cm^2/s/nm
# E_photon = hc/lambda;  hc = 1.9864e-16 J*nm
HC_JNM = 1.9864e-16
phot_dens = irr * (wl_nm[None, :] / HC_JNM) * 1e-4

edges = list(zip(WAVE1_A, WAVE2_A))
dup_count = np.array([edges.count(e) for e in edges], dtype=int)

def integrate_native(t_idx, lo_nm, hi_nm):
    mask = (wl_nm >= lo_nm) & (wl_nm <= hi_nm)
    if mask.sum() < 2:
        return 0.0
    return float(np.trapezoid(phot_dens[t_idx, mask], wl_nm[mask]))

LYALPHA_WINDOW = (121.0, 122.0)

sp_flux = np.zeros((NWAVE, ndate), dtype=np.float64)
for t_idx in range(ndate):
    raw = np.zeros(NWAVE)
    for k in range(NWAVE):
        if WAVE1_A[k] == WAVE2_A[k]:
            raw[k] = integrate_native(t_idx, *LYALPHA_WINDOW)
        else:
            raw[k] = integrate_native(t_idx, WAVE1_A[k]/10.0, WAVE2_A[k]/10.0)
    # Bin 11 (1200-1250 A) continuum = total - Lyman-alpha line
    raw[10] = max(raw[10] - raw[11], 0.0)
    # Apportion duplicate bins equally
    raw = raw / dup_count
    sp_flux[:, t_idx] = raw

uttime_hr = utc_s / 3600.0
days_in_year = 366.0 if YEAR % 4 == 0 else 365.0
yfrac = YEAR + (DOY - 1 + uttime_hr/24.0) / days_in_year
date_int = np.full(ndate, YEAR*1000 + DOY, dtype=np.int32)

import netCDF4 as nc
# netCDF3 classic requires the unlimited dim FIRST in each variable.
# TIEGCM declares Fortran arrays (ndate,nstruct) and (nwave,ndate,nstruct);
# in C/netCDF dim order that is reversed -> nstruct first.
with nc.Dataset(SEE_FILE, 'w', format='NETCDF3_CLASSIC') as ds:
    ds.createDimension('nstruct', None)
    ds.createDimension('dim1_DATE',    ndate)
    ds.createDimension('dim1_UTTIME',  ndate)
    ds.createDimension('dim1_YFRAC',   ndate)
    ds.createDimension('dim1_WAVE1',   NWAVE)
    ds.createDimension('dim1_WAVE2',   NWAVE)
    ds.createDimension('dim1_SP_FLUX', NWAVE)
    ds.createDimension('dim2_SP_FLUX', ndate)

    v = ds.createVariable('DATE',   'i4', ('dim1_DATE',))
    v[:] = date_int; v.long_name = 'yyyyddd integer'

    v = ds.createVariable('UTTIME', 'f8', ('nstruct','dim1_UTTIME'))
    v[0, :] = uttime_hr; v.units = 'hours'

    v = ds.createVariable('YFRAC',  'f8', ('nstruct','dim1_YFRAC'))
    v[0, :] = yfrac; v.long_name = 'fractional year'

    v = ds.createVariable('WAVE1',  'f8', ('nstruct','dim1_WAVE1'))
    v[0, :] = WAVE1_A; v.units = 'Angstrom'; v.long_name = 'short wavelength bound'

    v = ds.createVariable('WAVE2',  'f8', ('nstruct','dim1_WAVE2'))
    v[0, :] = WAVE2_A; v.units = 'Angstrom'; v.long_name = 'long wavelength bound'

    v = ds.createVariable('SP_FLUX','f8', ('nstruct','dim2_SP_FLUX','dim1_SP_FLUX'))
    # sp_flux is (nwave, ndate) in numpy -> transpose to (ndate, nwave) for C order
    v[0, :, :] = sp_flux.T; v.units = 'photons cm-2 s-1'

    ds.source = 'FISM2 60-s product rebinned to TIEGCM 37-bin EUVAC scheme'
    ds.event  = 'X5.1 flare 2025-11-11'
    ds.note   = 'Bin 11 has Lyman-alpha continuum correction; bins 19-21,22-24,25-26 use equal-split apportionment'

flare_idx = int(np.argmin(np.abs(utc_s - 10*3600)))
print(f"\nWrote {SEE_FILE}")
print(f"  ndate={ndate} time records, nwave={NWAVE} EUVAC bins")
print(f"  flare-peak (10:05 UT) Ly-alpha bin       : {sp_flux[11, flare_idx]:.3e} photons/cm2/s")
print(f"  flare-peak hardest-Xray bin (0.05-0.4nm) : {sp_flux[36, flare_idx]:.3e} photons/cm2/s")
""")

# ---------------------------------------------------------------------------
md(r"""## 4. Write the run namelist  ->  `tiegcm_flare_20251111.inp`

Output cadence is **1 minute** (`SECHIST = 0 0 1 0`). `STEP=30` s satisfies the
TIEGCM constraint that `SECHIST` be a multiple of `STEP`.

`SECFLDS` includes everything you requested that exists natively. Sigma_P,
Sigma_H, sigma_0, and the lat/lon subset are derived post-process from the
global secondary history.

**Caveat**: the namelist still references the bundled
`tiegcm_2.5x0.25_z7_mareqx_smin_prim.nc` startup file (Mar-equinox solar-min,
2002). For a publication-quality 2025 event run, spin up from a season/solar-
condition-matched primary history first. This is fine for a methodology test;
flag it before publishing.""")

code(r"""nml = f'''&tgcm_input
 LABEL = 'tiegcm-flare-20251111'
 START_YEAR = {YEAR}
 START_DAY = {DOY}
 CALENDAR_ADVANCE = 1
 SOURCE = '$TGCMDATA/tiegcm_2.5x0.25_z7_mareqx_smin_prim.nc'
 SOURCE_START = 81 0 0 0
 PRISTART = {DOY} 2 0 0
 PRISTOP  = {DOY} 16 0 0
 STEP = 30
 PRIHIST = 0 1 0 0
 OUTPUT  = 'tiegcm_flare_{YEAR}{DOY:03d}_prim_001.nc'
 MXHIST_PRIM = 24
 SECSTART = {DOY} 2 1 0
 SECSTOP  = {DOY} 16 0 0
 SECHIST  = 0 0 1 0
 SECOUT   = 'tiegcm_flare_{YEAR}{DOY:03d}_sech_001.nc'
 MXHIST_SECH = 60
 SECFLDS = 'TN' 'UN' 'VN' 'WN' 'O2' 'O1' 'N2' 'NO' 'N4S' 'HE' 'NE'
           'TE' 'TI' 'TEC' 'O2P' 'OP' 'POTEN' 'EY' 'EZ'
           'SIGMA_PED' 'SIGMA_HAL' 'JE13D' 'JE23D' 'JQR'
           'DEN' 'QJOULE' 'Z' 'ZG'
 GSWM_MI_DI_NCFILE  = '$TGCMDATA/gswm_diurn_2.5d_99km.nc'
 GSWM_MI_SDI_NCFILE = '$TGCMDATA/gswm_semi_2.5d_99km.nc'
 GSWM_NM_DI_NCFILE  = '$TGCMDATA/gswm_nonmig_diurn_2.5d_99km.nc'
 GSWM_NM_SDI_NCFILE = '$TGCMDATA/gswm_nonmig_semi_2.5d_99km.nc'
 POTENTIAL_MODEL = 'WEIMER'
 IMF_NCFILE = '/workspace/tiegcm-data/{IMF_FILE.name}'
 SEE_NCFILE = '/workspace/tiegcm-data/{SEE_FILE.name}'
 POWER   = {NAMELIST_INDICES['POWER']:.2f}
 CTPOTEN = {NAMELIST_INDICES['CTPOTEN']:.2f}
 F107    = {NAMELIST_INDICES['F107']:.2f}
 F107A   = {NAMELIST_INDICES['F107A']:.2f}
 CALC_HELIUM = 1
/
'''
NAMELIST.write_text(nml)
print(f"Wrote {NAMELIST}")
print("---")
print(nml)
""")

# ---------------------------------------------------------------------------
md(r"""## 5. Validation -- read back each file and sanity-check

The container will mount `data/` -> `/workspace/tiegcm-data/`, so the namelist
paths line up. The final cell prints the docker-run incantation.""")

code(r"""print("="*72); print("IMF file:"); print("="*72)
imf = xr.open_dataset(IMF_FILE)
print(imf, "\n")
print(f"  date range : {imf['date'].values[0]:.6f} .. {imf['date'].values[-1]:.6f}")
print(f"  Bz min/max : {imf['bz'].min().item():+.2f} .. {imf['bz'].max().item():+.2f} nT")

print("\n" + "="*72); print("SEE file:"); print("="*72)
see = xr.open_dataset(SEE_FILE)
print(see, "\n")
print(f"  WAVE1[0]={see['WAVE1'].values[0,0]:.2f} A   WAVE2[0]={see['WAVE2'].values[0,0]:.2f} A")
print(f"  WAVE1[-1]={see['WAVE1'].values[0,-1]:.2f} A   WAVE2[-1]={see['WAVE2'].values[0,-1]:.2f} A")
print(f"  flux shape (nstruct,ndate,nwave): {see['SP_FLUX'].shape}")
print(f"  Ly-alpha bin range over day: "
      f"{see['SP_FLUX'].values[0,:,11].min():.2e} .. {see['SP_FLUX'].values[0,:,11].max():.2e}")

print("\n" + "="*72); print("Namelist:"); print("="*72)
print(NAMELIST.read_text())

print("\nReady to run inside container:")
print(f"  docker run --rm -it --platform=linux/amd64 \\")
print(f"    -v {DATA}:/workspace/tiegcm-data \\")
print(f"    -v {ROOT.parent}/tiegcm-wd/run:/workspace/tiegcm-run \\")
print(f"    tiegcm:local")
print(f"  # then inside container:")
print(f"  TIEGCM_INP=/workspace/tiegcm-data/{NAMELIST.name} \\")
print(f"    bash $TIEGCMHOME/scripts/tiegcm-linux-local.job")
""")

# ---------------------------------------------------------------------------
nbf.write(nb, OUT)
print(f"Wrote {OUT}")
