# Scout chatbot system service

The unit is configured for Jetson user `elephant`, project directory `/home/elephant/aditya/patrick-realtime`, Conda environment `chatbot`, Shure input 26 and USB output 0. It starts at boot after network/audio targets and runs as the user with audio-group access. The launcher locates Conda and reads the project's .env through Python.

Copy the current project files to Jetson, including `scout_chatbot.service`, `run.sh`, and the updated prompt. Install after the audio fix has been synced and a manual run works:

```bash
cd /home/elephant/aditya/patrick-realtime
sudo chmod +x run.sh
systemd-analyze verify scout_chatbot.service
sudo install -m 644 scout_chatbot.service /etc/systemd/system/scout_chatbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now scout_chatbot.service
sudo systemctl status scout_chatbot.service --no-pager
```

Stop any manual Patrick instance before starting the service so both do not open the same microphone/speaker. Audio indices can change after reconnecting devices; check with `python -m patrick.realtime --devices` and edit the unit's PATRICK_INPUT_DEVICE/PATRICK_OUTPUT_DEVICE values if needed. Changing the unit requires daemon-reload and restart.

Failed processes restart after five seconds; the start-rate limiter is disabled so repeated startup failures continue retrying. The service can be stopped deliberately without restarting. It does not detect a live-but-hung Python process; no application heartbeat/watchdog is implemented.

```bash
sudo journalctl -u scout_chatbot.service -f
sudo systemctl restart scout_chatbot.service
sudo systemctl stop scout_chatbot.service
sudo systemctl disable --now scout_chatbot.service
```

The last two commands stop it now and optionally disable boot startup. A stop allows ten seconds before systemd terminates remaining processes. Because this is a system service, use systemctl rather than Ctrl+C.

Prompt changes: creation is attributed to Revobots rather than individual creators. Spoken company name is Reevobots; Giby is spoken as the letters G B. Written spellings are retained. A nonempty OPENAI_REALTIME_INSTRUCTIONS override replaces the prompt file and should be removed or updated to use these rules.
