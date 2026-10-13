# Patrick Realtime

GitHub: https://github.com/Aadi0032007/patrick-realtime.git

For Jetson Linux setup, see [the Jetson guide](docs/jetson-setup.md). `.gitignore` excludes credentials, environments, downloaded model weights, recordings, and build output; `.env.example` and `knowledge/combined.json` remain versioned.

Standalone CLI voice assistant: Vosk wake/end-of-utterance detection, OpenAI Realtime audio, Revobots PDF RAG, and OpenAI web search. Default voice: Cedar. Short prompt: `patrick/realtime_prompt.txt`.

## Run on this Windows machine

```bat
cd C:\Users\Aadi\aditya\patrick-realtime
run.cmd --input-device 2 --output-device 5
```

Say **Hey Patrick** and ask a question. Follow-ups need no wake phrase until 15 seconds idle. During generation/playback, only the whole word **stop** interrupts; other speech is discarded. The matched wake phrase prints in the terminal. Ctrl+C exits.

`run.cmd --devices` lists audio devices. `run.cmd --listen-test --input-device 2` tests Vosk offline. Add `--debug-audio` for transcripts and microphone levels. `--text` enables typed chat.

The local `.env` contains only required app settings and the existing OpenAI key. Never commit it. `.env.example` has no secrets. Restart after edits. Web search uses a separate OpenAI Responses request; returned source links print in the terminal. RAG indexes supported files throughout `knowledge/`, including subfolders. Add reference files and restart to load them. Existing source snapshots are consolidated in `knowledge/combined.json` with page provenance.

## Fresh environment

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This machine's environment may inherit installed packages from the existing base Python. For a portable installation, use the fresh-environment steps. No Qwen, Chatterbox, Ollama, or source-project imports are required.

## Tests

```bat
.venv\Scripts\python.exe -m unittest discover -s tests
```

Live API/audio behavior needs an interactive test. Network disconnects end the session; rerun to reconnect.

Say **stop** or **stop Patrick** while listening or during a reply to close the conversation. Buffered speech is discarded, and a fresh wake word is required after a brief silence. The microphone continues monitoring wake words locally; unwoken speech is not sent to OpenAI. Bare hey, hi, hello and the configured name also wake the assistant. Idle listening still closes after 15 seconds. Answers use a natural conversational style; documents and spoken citations are mentioned only if requested. Web source links remain visible in the terminal.

For source coverage and retrieval behavior, see [RAG details](docs/rag-details.md). Official website fallback searches https://revobots.ai/ when local Revobots knowledge lacks details. General web search remains available.
