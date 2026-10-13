# Set up Patrick Realtime on Jetson

Repository: https://github.com/Aadi0032007/patrick-realtime.git

Use a Jetson running 64-bit Ubuntu with Python **3.10 or newer**. These commands target a JetPack 6 / Ubuntu 22.04 installation. On an older JetPack image, use an existing Python 3.10+ environment rather than replacing Jetson's system Python. This assistant uses CPU Vosk plus cloud OpenAI audio/search; no CUDA, PyTorch, Qwen, or Chatterbox installation is required. Internet and an OpenAI API key with billing/model access are required for replies and web search.

## 1. Install system audio tools

```bash
uname -m
python3 --version
sudo apt-get update
sudo apt-get install -y git curl unzip python3-venv python3-dev build-essential \
  libportaudio2 portaudio19-dev libasound2-dev libffi-dev alsa-utils
```

Expect `aarch64` and Python 3.10+. The Python sounddevice package needs the Linux PortAudio library. Vosk provides Linux ARM64 support.

## 2. Clone and create a Linux environment

```bash
cd ~
git clone https://github.com/Aadi0032007/patrick-realtime.git
cd patrick-realtime
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If the repository is private, authenticate with GitHub when cloning. The local Windows project must be committed and pushed first for these files to be available on Jetson. Do not copy the Windows `.venv`; it cannot run on ARM Linux. If a `chatbot` Conda environment already provides Python 3.10+, you may activate it and install requirements there instead of creating this venv.

## 3. Download the local Vosk model

Model weights are excluded from Git. From the project root:

```bash
mkdir -p models
if [ ! -d models/vosk-model ]; then
  curl -fL https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip \
    -o /tmp/patrick-vosk-model.zip
  unzip -q /tmp/patrick-vosk-model.zip -d models
  mv models/vosk-model-small-en-us-0.15 models/vosk-model
fi
test -f models/vosk-model/am/final.mdl
test -f knowledge/combined.json
```

This is the small English model used for the wake phrase and pause-based endpointing. The bundled JSON is the page-numbered extraction of the Revobots reference PDF; the original PDF is not needed at runtime. The model is available from the [official Vosk model list](https://alphacephei.com/vosk/models).

## 4. Configure OpenAI

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

Set the API key locally and retain these settings:

```dotenv
OPENAI_API_KEY=your-key-here
OPENAI_REALTIME_MODEL=gpt-realtime-2.1
OPENAI_REALTIME_VOICE=cedar
RAG_KNOWLEDGE_DIR=knowledge
WEB_SEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=openai
WEB_SEARCH_MODEL=gpt-6-luna
SEARCH_TIMEOUT_SECONDS=30
```

Never put a real key in `.env.example` or commit `.env`. Shell environment variables override `.env`. Web search uses separate OpenAI Responses API requests and incurs additional API usage. Model access depends on the API account.

## 5. Select headset microphone and Smart monitor speakers

Connect the HyperX headset/dongle and the Smart monitor's HDMI/DisplayPort audio connection to the Jetson. In Ubuntu Sound settings, select the headset microphone as input and the monitor as output, and unmute both. Run these in the logged-in desktop session:

```bash
arecord -l
aplay -l
python -m patrick.realtime --devices
```

Find the input index for the headset and the output index for the monitor or the relevant HDMI audio device. **Do not reuse Windows indices 2 and 4.** Linux may expose desktop-routed audio as `pulse` or `default`; if individual device entries are missing, select the physical devices in Ubuntu Sound settings and use those routed defaults. An SSH/headless session may not have access to the desktop audio server.

Assign the indices displayed on your Jetson (replace the example placeholders with numbers):

```bash
read -r -p "Headset microphone device index: " MIC_INDEX
read -r -p "Smart monitor output device index: " SPEAKER_INDEX
```

Test the wake phrase and endpoint locally, without OpenAI:

```bash
python -m patrick.realtime --listen-test --input-device "$MIC_INDEX"
```

Say **Hey Patrick, tell me a joke**, then pause. Check that microphone levels rise, Vosk prints words, and `Turn detected` appears. Stop the test with Ctrl+C.

## 6. Verify and run

```bash
python -m unittest discover -s tests
python -m patrick.realtime --input-device "$MIC_INDEX" \
  --output-device "$SPEAKER_INDEX" --debug-audio
```

Say **Hey Patrick** to open a conversation. Ask follow-ups without repeating the wake phrase. After 15 seconds of idle listening, the wake phrase is required again. During replies, Vosk listens locally only for the whole word stop. Stop cancels speech, clears queued audio, and returns to fresh-wake mode; other speech does not interrupt. Wake logs print the matched phrase. PDF RAG answers Revobots questions; web search handles current public information and prints source links. Ctrl+C exits. Use `--text` to test API/tool behavior without audio devices.

For later runs:

```bash
cd ~/patrick-realtime
source .venv/bin/activate
python -m patrick.realtime --devices
# Use the current Linux device indices:
python -m patrick.realtime --input-device "$MIC_INDEX" --output-device "$SPEAKER_INDEX"
```

The `MIC_INDEX` and `SPEAKER_INDEX` variables must be set again in a new terminal; indices can change after reconnecting hardware. Run from the project root so model, prompt, index, and `.env` paths resolve correctly. `run.cmd` is for Windows only.

## Troubleshooting

- **No microphone level:** check selected input, hardware mute, Ubuntu input volume, and desktop-session access. Try the routed default input by omitting `--input-device`.
- **Unsupported sample rate:** this app uses 24 kHz mono PCM. Use the desktop `pulse`/`default` routed device to resample for hardware that only supports 48 kHz. Native ALSA `hw` entries may reject 24 kHz.
- **No monitor audio:** check Ubuntu's output profile, active HDMI/DisplayPort connection, and monitor volume. Omit `--output-device` to try the configured desktop default.
- **Vosk model missing:** verify `models/vosk-model/am/final.mdl`; use `--vosk-model PATH` for another location.
- **Python version or wheel errors:** check Python 3.10+, `uname -m`, and updated pip. Never reuse Windows package binaries on Jetson.
- **API rejects a model or key:** check `.env`, API billing/access, and any shell variables overriding your settings. Restart after edits.
- **Connection timeout:** check network stability and rerun for a new session. The app does not replay interrupted turns automatically.

This guide has been checked against the local app and its tests; it has not been executed on your Jetson. See the official [sounddevice installation documentation](https://python-sounddevice.readthedocs.io/en/latest/installation.html) and [Vosk installation documentation](https://alphacephei.com/vosk/install) for Linux dependency details.
