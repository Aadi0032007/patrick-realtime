# Wake and assistant name

Default: `python -m patrick.realtime` accepts “hey patrick”, “hi patrick” and “hello patrick”.

Custom name: `python -m patrick.realtime --name jarvis` accepts “hey jarvis”, “hi jarvis” and “hello jarvis”. Say “stop jarvis” to close. The selected name also sets the prompt identity and terminal labels.

`--wake-phrase "computer"` overrides the three greetings with one custom phrase. `--name` still controls assistant identity and the stop command. The idle timeout remains 15 seconds, and follow-ups do not require another wake phrase while the conversation is open.

Offline test: `python -m patrick.realtime --name jarvis --listen-test`.
