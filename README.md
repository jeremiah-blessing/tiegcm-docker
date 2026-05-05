# tiegcm-docker

Containerised build of [NCAR TIEGCM v3.0](https://github.com/NCAR/tiegcm)
(Thermosphere–Ionosphere–Electrodynamics General Circulation Model) using the
open-source toolchain (gfortran + OpenMPI + parallel HDF5 + parallel NetCDF +
ESMF 8.6).

The official environment described at
[tiegcm-docs.readthedocs.io](https://tiegcm-docs.readthedocs.io/en/latest/)
targets NCAR Derecho (Intel + cray-mpich) and NASA Pleiades (Intel + HPE-MPT).
Those stacks are site-licensed; this image substitutes the equivalent FOSS
libraries so TIEGCM can run anywhere Docker runs.

## Image

Pulled image (multi-arch, amd64 + arm64) is published to Docker Hub:

```
docker pull <DOCKERHUB_NAMESPACE>/tiegcm:3.0
docker pull <DOCKERHUB_NAMESPACE>/tiegcm:latest
```

Tags:

| Tag       | Meaning                                  |
| --------- | ---------------------------------------- |
| `latest`  | Latest successful build of `master`      |
| `master`  | Same as `latest`                         |
| `3.0`     | TIEGCM v3.0 release                      |
| `<sha>`   | Build of a specific TIEGCM commit        |

## Build locally

```bash
docker build -t tiegcm:3.0 .
# pin to a specific upstream ref:
docker build --build-arg TIEGCM_REF=v3.0 -t tiegcm:3.0 .
docker build --build-arg TIEGCM_REF=<commit-sha> -t tiegcm:3.0 .
```

Other build args (with sensible defaults):

| Arg                       | Default | What it controls                |
| ------------------------- | ------- | ------------------------------- |
| `UBUNTU_VERSION`          | 22.04   | Base image                      |
| `NETCDF_C_VERSION`        | 4.9.2   | netCDF-C source tarball         |
| `NETCDF_FORTRAN_VERSION`  | 4.6.1   | netCDF-Fortran source tarball   |
| `ESMF_VERSION`            | 8.6.0   | ESMF source tarball             |
| `TIEGCM_REPO`             | `https://github.com/NCAR/tiegcm.git` | TIEGCM remote |
| `TIEGCM_REF`              | master  | TIEGCM branch / tag / commit    |

## Data files

The model needs the TIEGCM v3.0 data set (multi-GB; not bundled). Download
from the link in the upstream README:

  https://bit.ly/4lddXZC

Untar somewhere on the host and bind-mount as `/data`.

## Run

```bash
docker run --rm -it \
  -v $PWD/tiegcm_data:/data \
  -v $PWD/work:/work \
  -e TGCMDATA=/data \
  <DOCKERHUB_NAMESPACE>/tiegcm:3.0 \
  mpirun --allow-run-as-root -np 4 \
    /opt/tiegcm/exec/tiegcm \
    /opt/tiegcm/scripts/tiegcm_default.inp
```

`tiegcmrun.py -e` (PBS submission) is a no-op in the container — there is no
scheduler. Use the direct `mpirun` form, or extend the entrypoint for
Slurm/PBS in your own derived image.

## What is **not** in the image

- Intel / Cray / HPE-MPT compilers and MPIs (site-licensed).
- Conda. The upstream `setEnvironment.sh` activates a conda env on
  Derecho/Pleiades; this image installs the same Python deps system-wide via
  `pip` from `tiegcmrun/requirements.txt`.
- PBS / qsub. The container is launched directly (Docker, k8s, Singularity).
- Data files (TGCMDATA). Mount them at `/data`.

## Validation note

The TIEGCM project officially validates only the Intel toolchain. gfortran
builds run and have been observed to produce sensible output, but bit-for-bit
reproducibility with reference benchmarks is **not** guaranteed.

## License

The Dockerfile and supporting scripts in this repository are MIT-licensed
(see `LICENSE`). The TIEGCM source code itself is governed by NCAR/HAO's
academic license; see <https://github.com/NCAR/tiegcm>.
