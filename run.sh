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

# Match the Shure by name because ALSA indices can change after reconnect/boot.
# An explicit CLI device index wins, and non-audio modes need no microphone.
PATRICK_RESOLVE_MIC=true
for argument in "$@"; do
  case "$argument" in
    --input-device|--input-device=*|--devices|--text|--help|-h) PATRICK_RESOLVE_MIC=false ;;
  esac
done
PATRICK_MIC_INDEX=0
if "$PATRICK_RESOLVE_MIC"; then
  PATRICK_MIC_INDEX="$(python - "${PATRICK_INPUT_DEVICE:-Shure}" <<'PY'
import sys
import sounddevice as sd

selector = sys.argv[1].strip()
if not selector:
    raise SystemExit('Microphone selector cannot be empty.')
try:
    index = int(selector)
except ValueError:
    matches = [(i, device['name']) for i, device in enumerate(sd.query_devices())
               if device['max_input_channels'] > 0 and selector.casefold() in device['name'].casefold()]
    if not matches:
        raise SystemExit(f'No input microphone matches {selector!r}. Connect the Shure or override --input-device.')
    if len(matches) != 1:
        raise SystemExit(f'Multiple input microphones match {selector!r}: {matches}. Use --input-device INDEX.')
    index = matches[0][0]
else:
    if sd.query_devices(index, 'input')['max_input_channels'] < 1:
        raise SystemExit(f'Device {index} is not a microphone.')
print(index)
PY
  )"
fi

PATRICK_VOSK_MODEL="models/vosk-model"
if [[ ! -f "$PATRICK_VOSK_MODEL/am/final.mdl" ]]; then
  PATRICK_VOSK_MODEL="models/vosk-model-small-en-us-0.15"
fi
exec python -m patrick.realtime \
  --name "${PATRICK_NAME:-Scout}" \
  --vosk-model "$PATRICK_VOSK_MODEL" \
  --input-device "$PATRICK_MIC_INDEX" \
  --output-device "${PATRICK_OUTPUT_DEVICE:-0}" "$@"
