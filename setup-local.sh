#!/usr/bin/env bash
# setup-local.sh — set up TIEGCM v3.0 native dependencies on local Linux
# (tested target: Ubuntu 22.04 amd64, Docker, miniconda already installed).
#
# Usage:
#   source setup-local.sh
#
# What it does (idempotent — safe to re-source):
#   1. Creates a conda env (default name: tiegcm) with gfortran, OpenMPI,
#      parallel HDF5, netCDF-Fortran, ESMF — all from conda-forge.
#   2. Installs Python deps from $TIEGCMHOME/tiegcmrun/requirements.txt.
#   3. Exports TIEGCMHOME, TIEGCMDATA, ESMFMKFILE for the current shell.
#
# Override defaults before sourcing if you want:
#   CONDA_ENV_NAME=mytiegcm TIEGCMHOME=/path/to/src source setup-local.sh

CONDA_ENV_NAME="${CONDA_ENV_NAME:-tiegcm}"
TIEGCMHOME_DEFAULT="/workspace/tiegcm"
TIEGCMDATA_DEFAULT="/workspace/tiegcm-data"

if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda not found in PATH. Install miniconda first." >&2
    return 1 2>/dev/null || exit 1
fi

eval "$(conda shell.bash hook)"

if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV_NAME"; then
    echo "Creating conda env '$CONDA_ENV_NAME' (this can take several minutes)..."
    conda create -y -n "$CONDA_ENV_NAME" --override-channels -c conda-forge \
        python=3.8 \
        fortran-compiler \
        "openmpi=4.*" \
        "hdf5=*=mpi_openmpi_*" \
        "netcdf-fortran=*=mpi_openmpi_*" \
        "esmf=*=mpi_openmpi_*" \
        make perl tcsh pip
    if [ $? -ne 0 ]; then
        echo "ERROR: conda env creation failed." >&2
        return 1 2>/dev/null || exit 1
    fi
else
    echo "Conda env '$CONDA_ENV_NAME' already exists — skipping create."
fi

conda activate "$CONDA_ENV_NAME"

export TIEGCMHOME="${TIEGCMHOME:-$TIEGCMHOME_DEFAULT}"
export TIEGCMDATA="${TIEGCMDATA:-$TIEGCMDATA_DEFAULT}"

ESMFMK="$(find "$CONDA_PREFIX/lib" -name esmf.mk 2>/dev/null | head -1)"
if [ -n "$ESMFMK" ]; then
    export ESMFMKFILE="$ESMFMK"
else
    echo "WARNING: esmf.mk not found under $CONDA_PREFIX/lib — ESMF install may be broken." >&2
fi

REQ="${TIEGCMHOME}/tiegcmrun/requirements.txt"
if [ -f "$REQ" ]; then
    pip install -r "$REQ"
else
    echo "NOTE: $REQ not found — skipped Python deps. Set TIEGCMHOME correctly and re-source if needed."
fi

mkdir -p "$TIEGCMDATA"

echo
echo "=== TIEGCM local env ready ==="
echo "  conda env    : $CONDA_DEFAULT_ENV  ($CONDA_PREFIX)"
echo "  TIEGCMHOME   : $TIEGCMHOME"
echo "  TIEGCMDATA   : $TIEGCMDATA"
echo "  ESMFMKFILE   : ${ESMFMKFILE:-<unset>}"
echo "  mpif90       : $(command -v mpif90)"
echo "  gfortran     : $(command -v gfortran)"
echo "  nf-config    : $(command -v nf-config)"
echo
echo "Next: cd \$TIEGCMHOME/scripts && bash tiegcm-linux-local.job"
