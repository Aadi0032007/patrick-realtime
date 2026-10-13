# USB audio sample-rate compatibility

The microphone and speaker use independently detected supported hardware formats. Each device's reported default rate is checked first, followed by alternative speech rates. Mono is preferred, with stereo conversion if required. Unsupported int16 mono/stereo devices return an explanatory error.

Hardware microphone PCM is continuously resampled to 24 kHz mono before Vosk and Realtime receive it. Realtime's 24 kHz mono output is resampled to the speaker rate and duplicated to stereo when required. Conversion stays outside the audio input callback and outside the network reader. Buffer limits still count Realtime bytes, preserving the existing duration bound. Existing wake, stop, name and RAG behavior remains unchanged.

Python 3.10–3.12 use the built-in audioop module. Python 3.13+ install audioop-lts through the updated requirements. No CUDA or neural model is needed for this conversion.

For the currently listed Shure microphone (26) and USB speaker (0), test locally first:

```bash
python -m patrick.realtime --name Scout --input-device 26 --listen-test
```

Then run `bash run.sh`, or:

```bash
python -m patrick.realtime --name Scout --wake-up Scout --input-device 26 --output-device 0
```

Startup reports the selected microphone and speaker hardware formats. Device indices can change after reconnecting hardware; use `--devices` to check them.
