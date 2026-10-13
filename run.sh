#!/usr/bin/env bash
# Launch from any directory. Additional arguments override the defaults below.
set -eo pipefail

PATRICK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$PATRICK_DIR"

if ! command -v conda >/dev/null 2>&1; then
  for candidate in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/mambaforge"; do
    if [[ -f "$candidate/etc/profile.d/conda.sh" ]]; then
      source "$candidate/etc/profile.d/conda.sh"
      break
    fi
  done
fi
if ! command -v conda >/dev/null 2>&1; then
  echo "Conda not found. Initialize Conda or source its etc/profile.d/conda.sh first." >&2
  exit 1
fi
PATRICK_CONDA_BASE="$(conda info --base)"
if [[ ! -f "$PATRICK_CONDA_BASE/etc/profile.d/conda.sh" ]]; then
  echo "Conda initialization script not found under $PATRICK_CONDA_BASE." >&2
  exit 1
fi
source "$PATRICK_CONDA_BASE/etc/profile.d/conda.sh"
conda activate "${PATRICK_CONDA_ENV:-chatbot}"

PATRICK_VOSK_MODEL="models/vosk-model"
if [[ ! -f "$PATRICK_VOSK_MODEL/am/final.mdl" ]]; then
  PATRICK_VOSK_MODEL="models/vosk-model-small-en-us-0.15"
fi
exec python -m patrick.realtime \
  --vosk-model "$PATRICK_VOSK_MODEL" \
  --input-device "${PATRICK_INPUT_DEVICE:-0}" \
  --output-device "${PATRICK_OUTPUT_DEVICE:-0}" "$@"
