# TIEGCM v3.0 — local Docker setup

A self-contained Docker image (Ubuntu 22.04 amd64 + Miniconda + conda-forge
gfortran/OpenMPI/HDF5/netCDF/ESMF) that builds and runs TIEGCM v3.0 locally.
Clones the latest TIEGCM `master` from `github.com/NCAR/tiegcm` at build time,
bakes in a v3.0-ready namelist, and runs out of the box on a fresh
container.

Tested on macOS (M3) under Rosetta emulation.

## Files in this folder

| File | Role |
|---|---|
| `Dockerfile` | image recipe — clones source, installs conda env, copies the files below |
| `Make.gfort_linux` | gfortran build flags pointing at the conda env |
| `tiegcm-linux-local.job` | build + run driver; honors `TIEGCM_INP` env var |
| `tiegcm_mareqx_smin_z11.inp` | v3.0-ready namelist (mareqx_smin, z=11, day 81→82) |
| `tiegcm-entrypoint.sh` | container entrypoint — activates conda env, sets env vars |
| `setup-local.sh` | (advanced) manual installer for bare-metal Linux, not used by Docker |
| `README.md` | this file |

## Prereqs

- **Docker Desktop** running.
- **macOS Apple Silicon (M-series)**: enable Rosetta emulation
  (Docker Desktop → Settings → General → "Use Rosetta for x86_64/amd64
  emulation on Apple Silicon"), give Docker ≥ 8 GB RAM and 4+ CPUs.
- ~20 GB free disk (image ~3–4 GB, plus data and run outputs).

## End-to-end recipe

### 1. Build the image (one-time per upstream change)

```bash
cd /Users/jeremiah/projects/tiegcm/local-linux-setup
docker build --platform=linux/amd64 -t tiegcm:local .
```

- ~20–40 min first time on M3 (mostly conda solve + ~1.5 GB of native libs).
- Always clones latest `master`. Use `--no-cache` to also redo the conda
  solve.
- A build-time check verifies `mpif90` / `gfortran` / `nf-config` /
  `ESMFMKFILE` are wired up — green build = working env.

### 2. Set up host working directory (one-time)

```bash
mkdir -p /Users/jeremiah/projects/tiegcm-wd/{data,run}
```

Layout:
```
/Users/jeremiah/projects/tiegcm-wd/
├── data/    →  /workspace/tiegcm-data    (input/startup files)
└── run/     →  /workspace/tiegcm-run     (execdir, binaries, histories, custom .inp)
```

### 3. Get the data files (one-time, ~536 MB)

You need 6 files in `tiegcm-wd/data/`. Four are direct HTTP; two are Globus.

**HTTP (run inside container after step 4):**
```bash
cd $TIEGCMDATA
for f in gswm_diurn_2.5d_99km.nc \
         gswm_semi_2.5d_99km.nc \
         gswm_nonmig_diurn_2.5d_99km.nc \
         gswm_nonmig_semi_2.5d_99km.nc; do
    wget -c "https://download.hao.ucar.edu/pub/tgcm/data/$f"
done
```

**Globus (download on your Mac, save into `tiegcm-wd/data/`):**

Visit https://bit.ly/4lddXZC (redirects to NCAR's "TIEGCM 3.0 data files"
Globus share). Sign in (Google ID works) and download:

| Globus path | Save as on Mac side |
|---|---|
| `/benchmarks/mareqx_smin.nc` | `tiegcm-wd/data/tiegcm_2.5x0.25_z7_mareqx_smin_prim.nc` (rename) |
| `/he_coefs_dres.nc` | `tiegcm-wd/data/he_coefs_dres.nc` |

Why rename: the namelist references the file by its v2.0-style long name.
Renaming at save time avoids any in-container edits.

Final state:
```
/Users/jeremiah/projects/tiegcm-wd/data/
├── gswm_diurn_2.5d_99km.nc                       (~92 MB)
├── gswm_nonmig_diurn_2.5d_99km.nc                (~92 MB)
├── gswm_nonmig_semi_2.5d_99km.nc                 (~92 MB)
├── gswm_semi_2.5d_99km.nc                        (~92 MB)
├── he_coefs_dres.nc                              (~6 MB)
└── tiegcm_2.5x0.25_z7_mareqx_smin_prim.nc        (~171 MB)
```

### 4. Run the container

```bash
docker run --rm -it --platform=linux/amd64 \
    -v /Users/jeremiah/projects/tiegcm-wd/data:/workspace/tiegcm-data \
    -v /Users/jeremiah/projects/tiegcm-wd/run:/workspace/tiegcm-run \
    tiegcm:local
```

You land in a bash shell with the `tiegcm` conda env active and
`TIEGCMHOME` / `TIEGCMDATA` / `ESMFMKFILE` / `LOGNAME` /
`OMPI_ALLOW_RUN_AS_ROOT` all set.

Tip — alias it in `~/.zshrc` on your Mac:
```bash
alias tiegcm-shell='docker run --rm -it --platform=linux/amd64 \
    -v /Users/jeremiah/projects/tiegcm-wd/data:/workspace/tiegcm-data \
    -v /Users/jeremiah/projects/tiegcm-wd/run:/workspace/tiegcm-run \
    tiegcm:local'
```

### 5. Build and run the model

```bash
cd $TIEGCMHOME/scripts
bash tiegcm-linux-local.job
```

That's it. The job script:
- Auto-picks `tiegcm_mareqx_smin_z11.inp` (baked-in v3.0-ready namelist).
- Uses `zitop=11` (matches v3.0 startup files — 73 vertical levels).
- Runs `mpirun -np 1 ./tiegcm` (default; raise with `TIEGCM_NPROC` on
  native amd64 — see env-var table below).

First-ever run = full build (~5–10 min) + 1-day integration
(15–45 min on M3 under Rosetta, faster on native amd64). Subsequent runs
reuse the binary.

#### Quick smoke run (10 timesteps, ~5 model-minutes)

To confirm the build is healthy without waiting for a full day-long
integration, point the job script at the bundled tiny namelist:

```bash
TIEGCM_INP=/workspace/tiegcm/scripts/tiegcm_test10.inp \
    bash /workspace/tiegcm/scripts/tiegcm-linux-local.job
```

This runs 10 × 30s timesteps (= 5 minutes of simulated time) and writes
one primary + a handful of secondary histories. Useful as a sanity check
after rebuilding the image or changing build flags.

Watch progress in another shell:
```bash
docker exec -it <container_id> bash -lc \
    'tail -f /workspace/tiegcm-run/default/tiegcm.out'
```

Success marker near the end: `Linux MPI run of ./tiegcm completed at ...`
plus new `.nc` files in the execdir:
```bash
ls -lh /workspace/tiegcm-run/default/*.nc
# → tiegcm_mareqx_smin_z11_prim_001.nc
#   tiegcm_mareqx_smin_z11_sech_001.nc
```

History files persist on your Mac at
`/Users/jeremiah/projects/tiegcm-wd/run/default/`.

## Customizing a run

### Use your own namelist

Drop your edited copy under `tiegcm-wd/run/default/` (already mounted), then:

```bash
export TIEGCM_INP=/workspace/tiegcm-run/default/myrun.inp
bash $TIEGCMHOME/scripts/tiegcm-linux-local.job
```

The env var overrides the baked-in default. Edits persist on Mac side, so
they survive image rebuilds.

A reasonable starting point is to `cp` the baked-in template:
```bash
cp $TIEGCMHOME/scripts/tiegcm_mareqx_smin_z11.inp \
   /workspace/tiegcm-run/default/myrun.inp
```

### Env-var overrides (no script edits needed)

The job script honors these env vars — set them before invoking to override
the baked-in defaults:

| Env var | Default | Effect |
|---|---|---|
| `TIEGCM_INP` | baked-in `tiegcm_mareqx_smin_z11.inp` | path to your custom namelist |
| `TIEGCM_ZITOP` | `11` | upper boundary pressure level (7 = low top, 11 = high top) |
| `TIEGCM_NPROC` | `1` | MPI process count. Default is 1 because >1 segfaults under Open MPI + Rosetta on Apple Silicon; on native amd64 (e.g. DigitalOcean droplets) you can safely raise it (`TIEGCM_NPROC=4`). |
| `TIEGCM_DEBUG` | `FALSE` | `TRUE` → `-Og -fcheck=all -fbacktrace` |
| `TIEGCM_EXECUTE` | `TRUE` | `FALSE` → build only, skip `mpirun` |

For other knobs (resolution, magnetic grid), edit these at the top of
`tiegcm-linux-local.job`:
- `horires` — 5 / 2.5 / 1.25 / 0.625 (degrees)
- `vertres` — 0.5 / 0.25 / 0.125 / 0.0625
- `mres` — 2 / 1 / 0.5 (magnetic grid resolution)

Changing `horires` / `vertres` / `zitop` regenerates `defs.h`, which triggers
a full rebuild on the next run.

### Multiple runs side by side

Each run config wants its own `execdir`. Edit the `execdir=` line in the job
script (or copy the script), e.g. `/workspace/tiegcm-run/highres/`. Don't
reuse one execdir across resolutions — defs.h changes force a full rebuild
and stomp prior binaries.

### Debug build

Set `debug="TRUE"` in the job script → `-Og -fcheck=all -fbacktrace`,
slower but with bounds checking and stack traces on crash.

## What persists vs. resets

| Across `docker build` | Across `docker run --rm` |
|---|---|
| ✅ `tiegcm-wd/data/` (host bind mount) | ✅ same |
| ✅ `tiegcm-wd/run/` — binaries, histories, your `.inp` | ✅ same |
| ❌ Anything under `/workspace/tiegcm/` (re-cloned from GitHub) | ❌ same |
| ❌ Anything under `/opt/conda/` (re-installed) | ✅ persists while container runs |
| ❌ Anything `apt-get install`ed at runtime | ❌ gone on `--rm` |

**Rule of thumb**: anything you want to keep, put under `tiegcm-wd/`.

## What's inside the image

| Path | Contents |
|---|---|
| `/opt/conda/envs/tiegcm/` | python 3.8, gfortran, OpenMPI, HDF5-MPI, netCDF, ESMF, numpy/xarray/netCDF4 |
| `/workspace/tiegcm/` | source (cloned latest master) |
| `/workspace/tiegcm/scripts/Make.gfort_linux` | gfortran build flags |
| `/workspace/tiegcm/scripts/tiegcm-linux-local.job` | build + run driver |
| `/workspace/tiegcm/scripts/tiegcm_mareqx_smin_z11.inp` | baked-in v3.0-ready namelist |
| `/workspace/tiegcm-run/` | execdir (host bind mount) |
| `/workspace/tiegcm-data/` | tgcmdata (host bind mount) |
| `/usr/local/bin/tiegcm-entrypoint.sh` | activates env + sets env vars |

Baked-in env vars: `TIEGCMHOME`, `TIEGCMDATA`, `ESMFMKFILE`, `LOGNAME=root`,
`USER=root`, `OMPI_ALLOW_RUN_AS_ROOT=1`, `OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`.

## Common gotchas (all fixed by the baked-in setup, listed for reference)

- **`mpirun has detected an attempt to run as root`** —
  `OMPI_ALLOW_RUN_AS_ROOT=1` is baked into the image's ENV. Won't recur.
- **`>>> INPUT inp_model: Cannot get LOGNAME environment variable`** —
  `LOGNAME=root` is baked in.
- **`No such file or directory at opening …/he_coefs_dres.nc`** — you need
  `he_coefs_dres.nc` because the namelist has `CALC_HELIUM = 1`. Download it
  from the Globus root.
- **`Source history not found`** — startup file timestamp doesn't match
  `SOURCE_START`. The baked-in `.inp` uses `81 0 0 0` matching the v3.0
  `mareqx_smin` file. If you bring a different startup file, run
  `ncdump -v mtime <file>` to see its actual `mtime` and align the `.inp`.
- **`Shutdown: stop message: PRISTART`** with `"starting model day must
  be equal to the starting calendar day"` — when `CALENDAR_ADVANCE = 1`,
  `START_DAY` must equal the day component of `PRISTART`. The baked-in
  `.inp` uses `START_DAY = 81` and `PRISTART = 81 0 0 0`. If you change
  one, change the other.
- **`gfortran: error: unrecognized command-line option '-r8'`** — you're
  using `Make.intel_linux` instead of `Make.gfort_linux`. Job script
  defaults to gfortran; only happens if you override.
- **OOM on resolution > 2.5°** — bump Docker Desktop RAM allocation, or
  drop `nproc` from 4 to 2.
- **`Program received signal SIGSEGV` early in run with `np=4`** — running
  multiple MPI ranks under Open MPI + Rosetta emulation on Apple Silicon
  segfaults TIEGCM during early dynamics setup (root cause: a
  domain-decomposition / message-passing interaction that doesn't tolerate
  Rosetta's memory semantics). The image now defaults to `nproc=1`. On
  native amd64 Linux you can safely bump it back up: `TIEGCM_NPROC=4 bash
  tiegcm-linux-local.job`.
- **Build context too large** — only matters if you're inside the repo root;
  this folder is the build context, so it's already tiny (~30 KB).

## Reference notes

- **Globus data share landing page**: https://bit.ly/4lddXZC
- **NCAR TGCM model page**: https://www.hao.ucar.edu/modeling/tgcm/
- **Wu et al. (2025), TIEGCM v3.0 paper**: https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2025JA034219
- **GCMprocpy** (Python post-processing for TIEGCM outputs):
  `pip install gcmprocpy` inside the container, then point it at
  `/workspace/tiegcm-run/default/` to plot histories. Docs:
  https://gcmprocpy.readthedocs.io

## (Advanced) Manual bare-metal install

If you want to skip Docker and install on a bare Linux machine, the
`setup-local.sh` script in this folder creates the same conda env directly.
Source it once, then use `tiegcm-linux-local.job` the same way.

```bash
cd /path/where/you/cloned/tiegcm
cp local-linux-setup/{setup-local.sh,Make.gfort_linux,tiegcm-linux-local.job,tiegcm_mareqx_smin_z11.inp} .
source setup-local.sh
cd scripts
bash tiegcm-linux-local.job
```

This requires miniconda already installed and on PATH. The Docker path is
recommended unless you have a specific reason to avoid containers.
