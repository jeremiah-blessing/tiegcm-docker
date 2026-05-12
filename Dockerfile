# syntax=docker/dockerfile:1.6
#
# TIEGCM v3.0 — local Linux (amd64) build environment.
# Clones the TIEGCM source from GitHub at build time (latest master HEAD).
# Build context is just this folder — no local repo checkout needed.
#
# Build (from this folder):
#   docker build --platform=linux/amd64 -t tiegcm:local .
#
# To force a fresh clone (bypass Docker's layer cache for the git step):
#   docker build --platform=linux/amd64 --no-cache -t tiegcm:local .
#
FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget bzip2 git make perl procps file vim less \
    && rm -rf /var/lib/apt/lists/*

# ---- Miniconda ----------------------------------------------------------
ARG MINICONDA_VERSION=latest
ENV CONDA_DIR=/opt/conda
ENV PATH=${CONDA_DIR}/bin:${PATH}

RUN curl -fsSL "https://repo.anaconda.com/miniconda/Miniconda3-${MINICONDA_VERSION}-Linux-x86_64.sh" -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p ${CONDA_DIR} \
    && rm /tmp/miniconda.sh \
    && conda config --set auto_activate_base false \
    && conda config --remove channels defaults 2>/dev/null || true \
    && conda config --add channels conda-forge \
    && conda config --set channel_priority strict \
    && conda clean -afy

# ---- TIEGCM conda env ---------------------------------------------------
ARG CONDA_ENV_NAME=tiegcm
ENV CONDA_ENV_NAME=${CONDA_ENV_NAME}

RUN conda create -y -n ${CONDA_ENV_NAME} --override-channels -c conda-forge \
        python=3.8 \
        fortran-compiler \
        "openmpi=4.*" \
        "hdf5=*=mpi_openmpi_*" \
        "netcdf-fortran=*=mpi_openmpi_*" \
        "esmf=*=mpi_openmpi_*" \
        make perl tcsh pip \
        numpy netCDF4 xarray jinja2 \
    && conda clean -afy

# ---- Clone TIEGCM source (latest master) --------------------------------
WORKDIR /workspace
RUN mkdir -p /workspace/tiegcm-run/default /workspace/tiegcm-data

# Cache-bust the clone: this ADD always re-fetches and its content (the
# latest commit SHA on master) invalidates the layer below whenever
# upstream advances. So a normal `docker build` picks up the latest master.
ADD https://api.github.com/repos/NCAR/tiegcm/commits/master /tmp/tiegcm-head.json

RUN git clone --depth 1 --branch master https://github.com/NCAR/tiegcm.git /workspace/tiegcm \
    && git -C /workspace/tiegcm log -1 --oneline

# ---- Stage local-Linux build files --------------------------------------
COPY Make.gfort_linux               /workspace/tiegcm/scripts/Make.gfort_linux
COPY tiegcm-linux-local.job         /workspace/tiegcm/scripts/tiegcm-linux-local.job
COPY tiegcm_mareqx_smin_z11.inp     /workspace/tiegcm/scripts/tiegcm_mareqx_smin_z11.inp
COPY tiegcm_test10.inp              /workspace/tiegcm/scripts/tiegcm_test10.inp
COPY setup-local.sh                 /workspace/setup-local.sh
COPY tiegcm-entrypoint.sh           /usr/local/bin/tiegcm-entrypoint.sh
RUN chmod +x /workspace/tiegcm/scripts/tiegcm-linux-local.job \
             /workspace/setup-local.sh \
             /usr/local/bin/tiegcm-entrypoint.sh

# Install Python deps pinned by the repo (in case they drift from what
# we already installed via conda).
RUN /opt/conda/envs/${CONDA_ENV_NAME}/bin/pip install --no-cache-dir \
        -r /workspace/tiegcm/tiegcmrun/requirements.txt

# ---- Env vars baked in --------------------------------------------------
# OpenMPI refuses to run as root by default; the container has no non-root
# user, so opt in explicitly. LOGNAME is read by TIEGCM at startup and is
# not set by default in a root container.
ENV TIEGCMHOME=/workspace/tiegcm \
    TIEGCMDATA=/workspace/tiegcm-data \
    OMPI_ALLOW_RUN_AS_ROOT=1 \
    OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
    LOGNAME=root \
    USER=root \
    PATH=/opt/conda/envs/tiegcm/bin:/opt/conda/bin:${PATH}

RUN { \
      echo "source /opt/conda/etc/profile.d/conda.sh"; \
      echo "conda activate ${CONDA_ENV_NAME}"; \
      echo "export TIEGCMHOME=/workspace/tiegcm"; \
      echo "export TIEGCMDATA=/workspace/tiegcm-data"; \
      echo 'export ESMFMKFILE=$(find /opt/conda/envs/'"${CONDA_ENV_NAME}"'/lib -maxdepth 2 -name esmf.mk 2>/dev/null | head -1)'; \
    } >> /root/.bashrc

# Build-time sanity check.
RUN /usr/local/bin/tiegcm-entrypoint.sh bash -lc \
    'command -v mpif90 && command -v gfortran && command -v nf-config && \
     test -f "$ESMFMKFILE" && echo "ESMFMKFILE=$ESMFMKFILE OK"'

ENTRYPOINT ["/usr/local/bin/tiegcm-entrypoint.sh"]
CMD ["bash", "-l"]
