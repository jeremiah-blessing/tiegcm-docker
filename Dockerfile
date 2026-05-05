# syntax=docker/dockerfile:1.6
#
# TIEGCM v3.0 — containerized build
# ----------------------------------
# Builds TIEGCM with the open-source toolchain (gfortran + OpenMPI + parallel
# HDF5 + parallel NetCDF-C/Fortran + ESMF). The Intel/Cray/HPE stacks
# referenced in the upstream docs (Derecho, Pleiades) are site-licensed and
# cannot be redistributed, so this image substitutes equivalent FOSS libs.
#
# Two-stage build:
#   1. `builder`  — installs OS toolchain, builds parallel netCDF + ESMF from
#                   source, clones NCAR/tiegcm at $TIEGCM_REF, compiles model.
#   2. `runtime`  — slim image with only the runtime libs and the model exe +
#                   tiegcmrun python tooling.
#
# Build:
#   docker build -t tiegcm:3.0 .                  # default branch (master)
#   docker build --build-arg TIEGCM_REF=v3.0 -t tiegcm:3.0 .   # tag
#   docker build --build-arg TIEGCM_REF=<sha> -t tiegcm:3.0 .  # commit
#
# Run:
#   docker run --rm -it \
#     -v /host/path/to/tiegcm_data:/data \
#     -v /host/path/to/work:/work \
#     -e TGCMDATA=/data \
#     tiegcm:3.0 \
#     mpirun --allow-run-as-root -np 4 /opt/tiegcm/exec/tiegcm \
#            /opt/tiegcm/scripts/tiegcm_default.inp
#
# Data files (NOT bundled — multi-GB, separate license):
#   https://bit.ly/4lddXZC   (the link from NCAR/tiegcm README.md)

ARG UBUNTU_VERSION=22.04
ARG NETCDF_C_VERSION=4.9.2
ARG NETCDF_FORTRAN_VERSION=4.6.1
ARG ESMF_VERSION=8.6.0
ARG TIEGCM_REPO=https://github.com/NCAR/tiegcm.git
ARG TIEGCM_REF=master

############################
# Stage 1: builder
############################
FROM ubuntu:${UBUNTU_VERSION} AS builder

ARG NETCDF_C_VERSION
ARG NETCDF_FORTRAN_VERSION
ARG ESMF_VERSION
ARG TIEGCM_REPO
ARG TIEGCM_REF
ARG MAKE_JOBS=4

ENV DEBIAN_FRONTEND=noninteractive \
    PREFIX=/opt/sw \
    PATH=/opt/sw/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LD_LIBRARY_PATH=/opt/sw/lib

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gfortran \
        gcc \
        g++ \
        make \
        cmake \
        perl \
        python3 \
        python3-pip \
        python3-venv \
        ca-certificates \
        curl \
        wget \
        git \
        m4 \
        pkg-config \
        zlib1g-dev \
        libcurl4-openssl-dev \
        libxml2-dev \
        libssl-dev \
        openmpi-bin \
        openmpi-common \
        libopenmpi-dev \
        libhdf5-openmpi-dev \
        hdf5-tools \
    && rm -rf /var/lib/apt/lists/*

ENV CC=mpicc \
    CXX=mpicxx \
    FC=mpifort \
    F77=mpifort \
    F90=mpifort

WORKDIR /tmp/build

# ---- netCDF-C (parallel) ----
RUN MULTIARCH="$(dpkg-architecture -qDEB_HOST_MULTIARCH)" \
 && export HDF5_DIR=/usr/lib/${MULTIARCH}/hdf5/openmpi \
 && export CPPFLAGS="-I/usr/include/hdf5/openmpi" \
 && export LDFLAGS="-L/usr/lib/${MULTIARCH}/hdf5/openmpi -Wl,-rpath,/usr/lib/${MULTIARCH}/hdf5/openmpi" \
 && export LIBS="-lhdf5 -lhdf5_hl" \
 && curl -fsSL "https://downloads.unidata.ucar.edu/netcdf-c/${NETCDF_C_VERSION}/netcdf-c-${NETCDF_C_VERSION}.tar.gz" \
      | tar -xz \
 && cd netcdf-c-${NETCDF_C_VERSION} \
 && ./configure --prefix=${PREFIX} \
        --enable-netcdf-4 \
        --enable-parallel-tests \
        --enable-shared \
        --disable-dap \
        --disable-byterange \
        --disable-libxml2 \
        --disable-nczarr-zip \
 && make -j${MAKE_JOBS} \
 && make install \
 && cd .. && rm -rf netcdf-c-${NETCDF_C_VERSION}

# ---- netCDF-Fortran (parallel) ----
RUN MULTIARCH="$(dpkg-architecture -qDEB_HOST_MULTIARCH)" \
 && export CPPFLAGS="-I${PREFIX}/include -I/usr/include/hdf5/openmpi" \
 && export LDFLAGS="-L${PREFIX}/lib -L/usr/lib/${MULTIARCH}/hdf5/openmpi -Wl,-rpath,${PREFIX}/lib -Wl,-rpath,/usr/lib/${MULTIARCH}/hdf5/openmpi" \
 && export LD_LIBRARY_PATH=${PREFIX}/lib:/usr/lib/${MULTIARCH}/hdf5/openmpi:${LD_LIBRARY_PATH} \
 && curl -fsSL "https://downloads.unidata.ucar.edu/netcdf-fortran/${NETCDF_FORTRAN_VERSION}/netcdf-fortran-${NETCDF_FORTRAN_VERSION}.tar.gz" \
      | tar -xz \
 && cd netcdf-fortran-${NETCDF_FORTRAN_VERSION} \
 && ./configure --prefix=${PREFIX} --enable-shared \
 && make -j${MAKE_JOBS} \
 && make install \
 && cd .. && rm -rf netcdf-fortran-${NETCDF_FORTRAN_VERSION}

# ---- ESMF ----
ENV ESMF_DIR=/tmp/build/esmf-${ESMF_VERSION} \
    ESMF_COMPILER=gfortran \
    ESMF_COMM=openmpi \
    ESMF_NETCDF=split \
    ESMF_NETCDF_INCLUDE=${PREFIX}/include \
    ESMF_NETCDF_LIBPATH=${PREFIX}/lib \
    ESMF_INSTALL_PREFIX=${PREFIX}/esmf \
    ESMF_INSTALL_HEADERDIR=include \
    ESMF_INSTALL_MODDIR=mod \
    ESMF_INSTALL_LIBDIR=lib \
    ESMF_INSTALL_BINDIR=bin \
    ESMF_BOPT=O \
    ESMF_OPTLEVEL=2

RUN curl -fsSL "https://github.com/esmf-org/esmf/archive/refs/tags/v${ESMF_VERSION}.tar.gz" \
      | tar -xz \
 && cd esmf-${ESMF_VERSION} \
 && make -j${MAKE_JOBS} lib \
 && make install \
 && cd .. && rm -rf esmf-${ESMF_VERSION}

ENV ESMFMKFILE=${PREFIX}/esmf/lib/esmf.mk \
    PATH=${PREFIX}/esmf/bin:${PREFIX}/bin:${PATH} \
    LD_LIBRARY_PATH=${PREFIX}/esmf/lib:${PREFIX}/lib:${LD_LIBRARY_PATH}

# ---- TIEGCM source ----
ENV TIEGCMHOME=/opt/tiegcm
RUN git clone --depth 1 --branch "${TIEGCM_REF}" "${TIEGCM_REPO}" "${TIEGCMHOME}" \
 || git clone "${TIEGCM_REPO}" "${TIEGCMHOME}" \
        && cd "${TIEGCMHOME}" \
        && git fetch --depth 1 origin "${TIEGCM_REF}" \
        && git checkout "${TIEGCM_REF}"

# Custom gfortran/OpenMPI build inputs (live in this repo, copied on top of
# the cloned tree).
COPY docker/Make.gfort_docker ${TIEGCMHOME}/scripts/Make.gfort_docker
COPY docker/tiegcm-docker.job ${TIEGCMHOME}/scripts/tiegcm-docker.job

ENV TGCMROOT=${TIEGCMHOME}
RUN bash ${TIEGCMHOME}/scripts/tiegcm-docker.job

############################
# Stage 2: runtime
############################
FROM ubuntu:${UBUNTU_VERSION} AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PREFIX=/opt/sw \
    TIEGCMHOME=/opt/tiegcm \
    TGCMROOT=/opt/tiegcm \
    TGCMDATA=/data \
    PATH=/opt/sw/esmf/bin:/opt/sw/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    OMPI_ALLOW_RUN_AS_ROOT=1 \
    OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
    LOGNAME=tiegcm \
    USER=tiegcm

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgfortran5 \
        libgomp1 \
        openmpi-bin \
        libopenmpi3 \
        libhdf5-openmpi-103 \
        libhdf5-openmpi-fortran-102 \
        zlib1g \
        libcurl4 \
        libxml2 \
        perl \
        python3 \
        python3-pip \
        netcdf-bin \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN printf '%s\n' \
        '/opt/sw/esmf/lib' \
        '/opt/sw/lib' \
        '/usr/lib/x86_64-linux-gnu/hdf5/openmpi' \
        '/usr/lib/aarch64-linux-gnu/hdf5/openmpi' \
        > /etc/ld.so.conf.d/tiegcm.conf \
 && /sbin/ldconfig

COPY --from=builder /opt/sw /opt/sw
COPY --from=builder /opt/tiegcm /opt/tiegcm

RUN pip3 install --no-cache-dir --break-system-packages \
        -r /opt/tiegcm/tiegcmrun/requirements.txt || \
    pip3 install --no-cache-dir \
        -r /opt/tiegcm/tiegcmrun/requirements.txt

WORKDIR /work
VOLUME ["/data", "/work"]

CMD ["/bin/bash"]
