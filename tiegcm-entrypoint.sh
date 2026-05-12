#!/bin/bash
# Container entrypoint: activate the tiegcm conda env, export TIEGCM env
# vars, then exec whatever the user asked for (CMD or `docker run` args).
set -e

CONDA_ENV_NAME="${CONDA_ENV_NAME:-tiegcm}"

# shellcheck disable=SC1091
source /opt/conda/etc/profile.d/conda.sh
conda activate "$CONDA_ENV_NAME"

export TIEGCMHOME="${TIEGCMHOME:-/workspace/tiegcm}"
export TIEGCMDATA="${TIEGCMDATA:-/workspace/tiegcm-data}"

if [ -z "${ESMFMKFILE:-}" ] || [ ! -f "${ESMFMKFILE:-}" ]; then
    ESMFMKFILE="$(find "/opt/conda/envs/$CONDA_ENV_NAME/lib" -maxdepth 2 -name esmf.mk 2>/dev/null | head -1)"
    export ESMFMKFILE
fi

mkdir -p "$TIEGCMDATA" "$(dirname "$TIEGCMHOME")/tiegcm-run"

exec "$@"
