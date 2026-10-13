# Wake and assistant name

Default: `python -m patrick.realtime` accepts “hey”, “hi”, “hello”, “patrick”, and greeting plus “patrick”.

Custom name: `python -m patrick.realtime --name jarvis` accepts “hey”, “hi”, “hello”, “jarvis”, and greeting plus “jarvis”. The selected name also sets the prompt identity and terminal labels.

`--wake-up` optionally chooses a different wake name; otherwise it follows `--name`. Bare greetings remain accepted. `--wake-phrase "computer"` overrides all default wake words with one exact custom phrase. These two options are mutually exclusive.

Any recognized whole word “stop” closes locally while the microphone is listening; “stop NAME” also works. Words such as “stopwatch” do not close it. The idle timeout remains 15 seconds. Follow-ups require no wake phrase while open, and capture stays paused while the assistant speaks.

Offline test: `python -m patrick.realtime --name jarvis --listen-test`.
