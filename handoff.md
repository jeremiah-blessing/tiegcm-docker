# Handoff — running TIEGCM from the published image

This document picks up **after** the Docker image has been built and published.
Goal: get from "image is on Docker Hub" → "model output netCDF files on
disk."

## Current state (as of handoff)

- Repo: <https://github.com/jeremiah-blessing/tiegcm-docker> (master branch)
- CI: `.github/workflows/docker.yml` builds `linux/amd64` and pushes to
  Docker Hub on every push to `master` and on tag pushes
- Image: `vjeremiah/tiegcm-docker:latest` (also tagged `master` and `sha-<short>`)
- Image size: ~210 MB compressed / ~886 MB on disk
- The image was verified to run end-to-end up to "needs input data" — the
  binary launches, prints its banner, and exits cleanly when no data is
  mounted.
- Apple Silicon note: the image is `linux/amd64` only. On an M-series Mac,
  pull and run with `--platform linux/amd64` so Docker Desktop uses Rosetta.

```bash
docker pull --platform linux/amd64 vjeremiah/tiegcm-docker:latest
```

## What "running TIEGCM" actually requires

Three things, in order:

1. **A namelist file** — the configuration. The image ships
   `/opt/tiegcm/scripts/tiegcm_default.inp` which is the canonical March
   Equinox / Solar Minimum 1-day benchmark at 2.5°×0.25°.
2. **Input data files (netCDF)** — these are NOT in the image. They are
   physics inputs (climatologies, tidal data, geomagnetic indices) and a
   "startup history" file with the model's initial state.
3. **A working directory** — where the model writes output history files.

## Required input data files

For the default namelist, you need six files in your data dir:

| File                                              | What it is                                                | Approx size |
| ------------------------------------------------- | --------------------------------------------------------- | ----------- |
| `tiegcm_2.5x0.25_z7_mareqx_smin_prim.nc`          | Startup history — initial state on day 80                 | ~200 MB     |
| `gswm_diurn_2.5d_99km.nc`                         | GSWM migrating diurnal tides @ 99 km                      | ~10 MB      |
| `gswm_semi_2.5d_99km.nc`                          | GSWM migrating semidiurnal tides                          | ~10 MB      |
| `gswm_nonmig_diurn_2.5d_99km.nc`                  | GSWM non-migrating diurnal tides                          | ~10 MB      |
| `gswm_nonmig_semi_2.5d_99km.nc`                   | GSWM non-migrating semidiurnal tides                      | ~10 MB      |
| `he_coefs_dres.nc`                                | Helium upper-boundary flux coefficients (CALC_HELIUM=1)   | ~1 MB       |

A few hundred MB total for the default benchmark. If you can't get
`he_coefs_dres.nc`, set `CALC_HELIUM = 0` in your namelist to disable Helium
calculation and skip the file. The full upstream data set
is multi-GB and includes startup files and tidal data for every supported
resolution (5°, 2.5°, 1.25°, 0.625°) plus geomagnetic forcing data
(IMF/Kp/F10.7).

### Where to get them

The NCAR/tiegcm README points to a single share link:

  <https://bit.ly/4lddXZC>

This redirects to a public file share (Google Drive / similar). It cannot be
`wget`'d directly because of the share UI — download manually through a
browser, then extract to a local directory. Verify the five files above are
present.

### Can I use mock / synthetic data instead?

**Practically, no.** The startup history file is a snapshot of every
prognostic field (temperature, winds, ion densities, etc.) on the model's
3-D grid. The GSWM files are precomputed tidal amplitudes/phases from a
specific climate model. Both have specific:

- Variable names the Fortran code expects (`TN`, `UN`, `VN`, `O2`, etc.)
- Grid dimensions matching the resolution compiled into `defs.h`
- Physically meaningful values — zeros or random numbers crash the
  semi-implicit solver within a few timesteps with floating-point exceptions
  or NaN propagation

So the practical options are:

1. **Use the real data** (recommended). It's the only path to scientifically
   meaningful output.
2. **Smoke-test only.** Confirm the binary launches and parses a namelist —
   no actual simulation. See "Smoke test" below. You already did this once.
3. **Borrow a startup file from a colleague at NCAR/HAO.** If you only need
   a smoke run that compiles + initializes + dies on missing forcing data,
   even a wrong-resolution startup file will get you past the
   "binary works" point but it will fail with a clear error during the
   timestepping loop.

There is no realistic synthetic-data path.

## Layout: set up your run directory

```bash
cd ~/projects/tiegcm-docker      # or anywhere — this dir is just for runs
mkdir -p run/data run/work
# Download data from https://bit.ly/4lddXZC, extract into run/data/
ls run/data/                     # should show the 5 files above (and more)
```

You can pick any host directory; only what you mount into the container
matters.

## Pre-flight check

Before kicking off a long run, verify the data is mounted and findable:

```bash
docker run --rm --platform linux/amd64 \
  -v "$PWD/run/data:/data" \
  vjeremiah/tiegcm-docker:latest \
  bash -c 'for f in \
      /data/tiegcm_2.5x0.25_z7_mareqx_smin_prim.nc \
      /data/gswm_diurn_2.5d_99km.nc \
      /data/gswm_semi_2.5d_99km.nc \
      /data/gswm_nonmig_diurn_2.5d_99km.nc \
      /data/gswm_nonmig_semi_2.5d_99km.nc; do
    [ -f "$f" ] && echo "OK   $f" || echo "MISS $f"
  done'
```

Every line should say `OK`. If you see `MISS`, the download is incomplete.

## Run the default 1-day benchmark

```bash
docker run --rm -it --platform linux/amd64 \
  -v "$PWD/run/data:/data" \
  -v "$PWD/run/work:/work" \
  -e TGCMDATA=/data \
  -w /work \
  vjeremiah/tiegcm-docker:latest \
  mpirun --allow-run-as-root -np 4 \
    /opt/tiegcm/exec/tiegcm \
    /opt/tiegcm/scripts/tiegcm_default.inp
```

Flag-by-flag:

- `--platform linux/amd64` — needed on Apple Silicon (Rosetta).
- `-v $PWD/run/data:/data` — host data → `/data` in container.
- `-v $PWD/run/work:/work` — host work dir → `/work`. Output is written here.
- `-e TGCMDATA=/data` — the namelist uses `$TGCMDATA` to resolve input paths.
- `-w /work` — model writes output relative to cwd.
- `-np 4` — image was built for `nproc=4`. Don't exceed that.

Expected runtime:

| Host                              | ~Wall time for default 1-day run |
| --------------------------------- | -------------------------------- |
| Linux x86_64 server, native       | 5–15 min                         |
| Apple Silicon under Rosetta       | 20–60 min                        |
| Cloud VM (4 vCPU, e.g. EC2 c7i)   | 8–20 min                         |

## No-data verification suite (~30 sec)

You can verify the entire toolchain is healthy without downloading any data
files at all. This tests everything except the physics/timestepping loop —
which is the only piece that genuinely needs real input.

```bash
docker run --rm --platform linux/amd64 vjeremiah/tiegcm-docker:latest bash -c '
echo "=== 1. Binary ==="
ls -lh /opt/tiegcm/exec/tiegcm
echo "=== 2. Linked libraries ==="
ldd /opt/tiegcm/exec/tiegcm | grep -E "netcdf|esmf|mpi|hdf5|gfortran" | sort -u
echo "=== 3. MPI launches 4 ranks ==="
mpirun --allow-run-as-root -np 4 hostname
echo "=== 4. Python tooling ==="
python3 -c "import numpy, netCDF4, xarray, jinja2; print(\"ok\")"
echo "=== 5. netCDF version ==="
ncdump 2>&1 | tail -1
'
```

Expected output: every section produces output, no errors. Specifically:
- `libnetcdf.so`, `libnetcdff.so`, `libesmf.so`, `libmpi.so`, `libhdf5_*` all
  resolve from `/opt/sw` or `/lib/x86_64-linux-gnu/`
- 4 hostname lines (one per MPI rank)
- `ok` from the Python imports
- `netcdf library version 4.9.2`

### How far the model itself can get without data

Run the model with the default namelist but no data mounted:

```bash
docker run --rm --platform linux/amd64 vjeremiah/tiegcm-docker:latest bash -c '
mpirun --allow-run-as-root -np 4 \
  /opt/tiegcm/exec/tiegcm \
  /opt/tiegcm/scripts/tiegcm_default.inp 2>&1 | tail -20
'
```

You should see:

1. `Begin execution of tiegcm_trunk` banner from each rank
2. `Reading namelist input data from .../tiegcm_default.inp`
3. The full namelist echoed back
4. `Completed successful read of namelist inputs.`
5. `>>> Shutdown: stop message: No such file or directory at opening
   /data/he_coefs_dres.nc`

That last line is the **expected** failure — you've reached the point where
real data is required. Everything before it is verified working.

If you see errors before step 5 (e.g. `Cannot get LOGNAME environment
variable`), pull a newer image — `LOGNAME` is now baked into the runtime
ENV.

## Inspect the output

After a successful run, `run/work/` contains two netCDF files:

```
tiegcm_2.5x0.25_z7_mareqx_smin_prim_001.nc   # primary history (full state, low cadence)
tiegcm_2.5x0.25_z7_mareqx_smin_sech_001.nc   # secondary history (diagnostic fields, hourly)
```

Look at the structure with `ncdump` (already in the image):

```bash
docker run --rm --platform linux/amd64 \
  -v "$PWD/run/work:/work" \
  vjeremiah/tiegcm-docker:latest \
  ncdump -h /work/tiegcm_2.5x0.25_z7_mareqx_smin_sech_001.nc | head -50
```

For real plots/analysis, see [GCMProcpy](https://github.com/NCAR/gcmprocpy)
(NCAR's official Python post-processor) or open the files in any netCDF tool
(xarray, ncview, Panoply, MATLAB, IDL).

## Common errors and fixes

| Symptom                                           | Cause / fix                                                                 |
| ------------------------------------------------- | --------------------------------------------------------------------------- |
| `no matching manifest for linux/arm64`            | Forgot `--platform linux/amd64` on Apple Silicon                            |
| `Cannot find SOURCE file ... prim.nc`             | `TGCMDATA` env var not set or data not mounted at expected path             |
| `Cannot find file ... gswm_*.nc`                  | One of the GSWM files is missing from the data download                     |
| `No such file or directory at opening ... he_coefs_dres.nc` | Helium coefficients file missing — either add it to data dir or set `CALC_HELIUM = 0` in the namelist |
| `Cannot get LOGNAME environment variable`         | Old image without the LOGNAME baked in — `docker pull` a newer `latest`, or pass `-e LOGNAME=tiegcm`   |
| Model crashes within first few timesteps with NaN | Grid mismatch — the startup file resolution doesn't match `defs.h` compiled into the image (2.5° × 0.25°) |
| `Cannot allocate memory` / OOM kill               | Bump Docker Desktop memory to 6+ GB (Settings → Resources → Memory)         |
| `mpirun ... was unable to find ...`               | Don't change `-np` higher than 4 — the image was built for 4 ranks         |
| Run is much slower than the table above           | On Apple Silicon, that's normal under Rosetta. On Linux, check CPU contention |

## Going beyond the default

### Different namelist (shorter test run)

```bash
mkdir -p run/work
docker run --rm --platform linux/amd64 vjeremiah/tiegcm-docker:latest \
  cat /opt/tiegcm/scripts/tiegcm_default.inp > run/work/short.inp

# Edit run/work/short.inp:
#   PRISTOP = 80 1 0 0          # stop after 1 hour instead of 1 day
#   PRIHIST = 0 0 30 0          # write history every 30 minutes
#   OUTPUT  = 'short_prim.nc'
#   SECOUT  = 'short_sech.nc'

docker run --rm -it --platform linux/amd64 \
  -v "$PWD/run/data:/data" \
  -v "$PWD/run/work:/work" \
  -e TGCMDATA=/data \
  -w /work \
  vjeremiah/tiegcm-docker:latest \
  mpirun --allow-run-as-root -np 4 \
    /opt/tiegcm/exec/tiegcm \
    /work/short.inp
```

### Different resolution

The image is fixed at `2.5° × 0.25°` (set by `defs.h` baked in at build
time). To run a different resolution you have to rebuild:

1. Edit `docker/tiegcm-docker.job` in the repo:
   - `horires="5"` `vertres="0.5"` for the 5° benchmark
   - `horires="1.25"` `vertres="0.125"` for higher resolution
2. Push to master (or `gh workflow run docker.yml -f tiegcm_ref=master`).
3. Pull the new image, mount the matching startup file (e.g.
   `tiegcm_5.0_z7_mareqx_smin_prim.nc` from the same data download).

### Pin to a specific TIEGCM release / commit

```bash
gh workflow run docker.yml -R jeremiah-blessing/tiegcm-docker \
   -f tiegcm_ref=v3.0
# or
gh workflow run docker.yml -R jeremiah-blessing/tiegcm-docker \
   -f tiegcm_ref=9b3a0e7
```

The workflow's `Dockerfile` does `git clone --branch ${TIEGCM_REF}` for tags
and branches; if you pass a SHA, the fallback `git fetch && git checkout`
handles it.

## Reference

- TIEGCM docs: <https://tiegcm-docs.readthedocs.io/en/latest/>
- Source: <https://github.com/NCAR/tiegcm>
- Data: <https://bit.ly/4lddXZC>
- Post-processing (Python): <https://github.com/NCAR/gcmprocpy>
- This image's repo: <https://github.com/jeremiah-blessing/tiegcm-docker>
- This image on Docker Hub: <https://hub.docker.com/r/vjeremiah/tiegcm-docker>

## Validation caveat

The TIEGCM project officially validates only the Intel toolchain (Derecho /
Pleiades). This image uses gfortran + OpenMPI. Output is observed to be
reasonable but is **not bit-for-bit identical** to NCAR's reference results.
For publication-grade science runs, use the official NCAR build on Derecho
or a system with the Intel oneAPI compilers. For development, prototyping,
education, and CI of downstream tooling, this image is fine.
