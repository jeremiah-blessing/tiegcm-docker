# CLAUDE.md — context for tiegcm-docker

This repo packages **TIEGCM v3.0** (NCAR's Thermosphere-Ionosphere-Electrodynamics GCM) into a self-contained Docker image. The image clones the latest NCAR/tiegcm master at build time, sets up a conda-forge env with all native deps (gfortran, OpenMPI, parallel HDF5, netCDF-Fortran, ESMF), and ships a job script + v3.0-ready namelist for one-shot runs.

Primary target: local builds on Mac M-series (amd64 via Rosetta) and DigitalOcean droplets (native amd64).

## Sibling repos on this machine

Both are siblings of this repo under `/Users/jeremiah/projects/`. Read from them; don't push to them.

- **`/Users/jeremiah/projects/tiegcm/`** — NCAR/tiegcm source clone (`origin` = `git@github.com:NCAR/tiegcm.git`, not a fork). Read-only for our purposes. Use it to: inspect Fortran source (`src/*.F`), see canonical job scripts (`scripts/`), check namelist semantics, debug model errors. The image clones this same repo from GitHub at build time, so the local clone is just for reading — never bind-mount it.
- **`/Users/jeremiah/projects/tiegcm-docs/`** — the deployed TIEGCM v3.0 documentation (Sphinx source → ReadTheDocs at `tiegcm-docs.readthedocs.io`). Use it to: look up namelist parameter docs, model description sections, v3.0 release notes. When a question is about "what does this namelist field mean" or "how does the dynamo work," check `docs/source/` here first.

## What lives in this repo

| File | Purpose |
|---|---|
| `Dockerfile` | Image recipe (Ubuntu 22.04 + miniconda + tiegcm clone) |
| `setup-local.sh` | Bare-metal env setup (alt to Docker) |
| `tiegcm-entrypoint.sh` | Container ENTRYPOINT that activates conda env |
| `Make.gfort_linux` | gfortran build flags pointing at `$CONDA_PREFIX` |
| `tiegcm-linux-local.job` | Build + run driver; honors `TIEGCM_*` env vars |
| `tiegcm_mareqx_smin_z11.inp` | Baked-in v3.0 namelist (1-day run from mareqx smin startup) |
| `tiegcm_test10.inp` | 10-timestep smoke namelist for quick verification |
| `.github/workflows/docker.yml` | Build & push amd64 image to Docker Hub |
| `README.md` | End-to-end recipe + gotchas (keep this current) |

## Hard-won gotchas (already baked in — don't re-discover)

These were painful to learn. The baked-in setup fixes each; only revisit if symptoms recur:

1. **`nproc=1` is the default.** Multi-rank Open MPI segfaults during early dynamics setup under Rosetta on Apple Silicon. On native amd64 hosts (DigitalOcean), override with `TIEGCM_NPROC=4`. Don't change the default — it'd break Mac users.
2. **`START_DAY` must equal `PRISTART` day** when `CALENDAR_ADVANCE=1`. The baked `.inp` uses `81` for both. If you change one, change the other or set `CALENDAR_ADVANCE=0`.
3. **`he_coefs_dres.nc` is required** when the namelist has `CALC_HELIUM = 1`. It's only on Globus; the README data-shopping section flags this.
4. **The v3.0 startup file is z=11** (73 levels) even though its filename says `z7`. We renamed the local copy to match the namelist's `SOURCE` path; don't be confused by the filename. Build defaults to `zitop=11` to match.
5. **OpenMPI refuses to run as root** by default. Image sets `OMPI_ALLOW_RUN_AS_ROOT=1`/`_CONFIRM=1` plus `LOGNAME=root`/`USER=root` so the model finds `getenv("LOGNAME")`.
6. **Build context is just this folder** — the Dockerfile clones tiegcm itself from GitHub. Don't `cd` into the parent before `docker build`.

If a user hits one of these symptoms anyway, the fix is already in code — first check whether they're using an out-of-date image (haven't rebuilt since the baked-in fix) before re-debugging from scratch.

## Build + run patterns

**Build image (local):**
```bash
docker build --platform=linux/amd64 -t tiegcm:local .
```

**Run container (with persistent host-side work dir):**
```bash
docker run --rm -it --platform=linux/amd64 \
  -v /Users/jeremiah/projects/tiegcm-wd/data:/workspace/tiegcm-data \
  -v /Users/jeremiah/projects/tiegcm-wd/run:/workspace/tiegcm-run \
  tiegcm:local
```

**Inside container — full run:**
```bash
cd $TIEGCMHOME/scripts && bash tiegcm-linux-local.job
```

**Inside container — 10-step smoke run:**
```bash
TIEGCM_INP=/workspace/tiegcm/scripts/tiegcm_test10.inp \
  bash $TIEGCMHOME/scripts/tiegcm-linux-local.job
```

## Where outputs go

History files (`*.nc`) land in `/workspace/tiegcm-run/default/` inside the container, which maps to `/Users/jeremiah/projects/tiegcm-wd/run/default/` on the host. They persist across container destruction; the image itself stays clean.

## Editing rules

- **README.md is user-facing** — keep it tight, recipe-first, every gotcha already in the baked image goes in the "Common gotchas" section so users know what's already fixed.
- **`Dockerfile`, `Make.gfort_linux`, `tiegcm-linux-local.job`, `*.inp`** are the actual artifacts — image rebuild required for changes to take effect on a host that pulls.
- **CI workflow** at `.github/workflows/docker.yml` pushes `linux/amd64` to Docker Hub on commits to `master`. Smoke test verifies env + key files; the binary itself isn't built at CI time (built at runtime by the job script).
- **Don't add `LICENSE` or extra meta files** unless the user asks — repo was deliberately stripped to essentials.

## What this repo is NOT for

- Running TIEGCM in HPC (Derecho, Pleiades). NCAR provides their own job scripts in the upstream `scripts/` folder. This repo is for self-contained, single-machine deployments.
- Modifying TIEGCM source. The image clones master fresh on every build; any source change needs to go upstream to NCAR/tiegcm first or be patched in via a Dockerfile RUN step.
- Bundling data files in the image. Data lives on a host bind-mount. A "fat image" variant (Dockerfile.full) bundling `tiegcm-data/` was discussed but not yet implemented — ask before adding it.

## When in doubt

- Namelist questions → read `/Users/jeremiah/projects/tiegcm-docs/docs/source/`
- Source code questions → grep `/Users/jeremiah/projects/tiegcm/src/`
- "Why does the image do X" → check `Dockerfile` comments + this file's "gotchas" section
- "How do I customize a run" → `README.md` Customizing a run section is the canonical answer
