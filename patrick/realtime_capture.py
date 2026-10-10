"""Local Vosk wake phrase and acoustic utterance endpointing for Realtime."""
from collections import deque
import json
import queue
import threading
import math
import struct
import time
from pathlib import Path

from .endpoint import PhraseWakeDetector, normalize


class VoskTurn:
    """Keep pre-roll, activate on a wake phrase, finish on Vosk's final result."""
    def __init__(self, recognizer, wake_phrase="hey patrick", rate=24000, require_wake=True):
        self.recognizer = recognizer
        self.wake = PhraseWakeDetector(wake_phrase)
        self.rate = rate
        self.reset()
        self.active = not require_wake

    def reset(self):
        self.recognizer.Reset()
        self.pre_roll = deque(maxlen=150)  # Three seconds of 20 ms frames.
        self.chunks = []
        self.active = False
        self.question = False
        self.duration = 0
        self.last_text = ""
        self.last_final = False
        self.idle = 0

    def feed(self, pcm):
        self.pre_roll.append(pcm)
        final = self.recognizer.AcceptWaveform(pcm)
        result = json.loads(self.recognizer.Result() if final else self.recognizer.PartialResult())
        text = normalize(result.get("text" if final else "partial", ""))
        previous_text = self.last_text
        self.last_text, self.last_final = text, final
        command = text
        if command.startswith(self.wake.phrase + " "):
            command = command[len(self.wake.phrase) + 1:]
        # Close locally before command audio is sent to OpenAI.
        if (self.active or self.wake.detect(text)) and command == "stop patrick":
            self.reset()
            raise ConversationStopped("Conversation closed. Say Hey Patrick to reopen it.")
        if not self.active:
            if not self.wake.detect(text):
                return None
            self.active = True
            self.chunks = list(self.pre_roll)
        else:
            self.chunks.append(pcm)
        self.duration += len(pcm) / (self.rate * 2)
        self.idle += len(pcm) / (self.rate * 2)
        _, found, after = text.partition(self.wake.phrase)
        content = after.strip() if found else text
        if content:
            if not self.question:
                self.chunks = list(self.pre_roll)
                self.duration = len(pcm) / (self.rate * 2)
            self.question = True
            if text != previous_text or final:
                self.idle = 0
        # A wake-only final is not the question: retain the next utterance.
        if final and self.question:
            audio = b"".join(self.chunks)
            self.reset()
            return audio
        if self.idle >= 15:
            self.reset()
            raise IdleExpired("15 seconds idle. Say Hey Patrick to reopen the conversation.")
        if self.duration >= 30:
            # Never send a truncated or wake-only turn automatically.
            self.reset()
            raise TimeoutError("No completed question detected. Say Hey Patrick and try again.")
        return None


def pcm_level(pcm):
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    return math.sqrt(sum(value * value for value in samples) / max(1, len(samples))) / 32768


class IdleExpired(TimeoutError):
    pass


class ConversationStopped(TimeoutError):
    """Local command that returns the voice loop to wake-only mode."""


def capture_turn(sd, model, recognizer_factory, input_device, wake_phrase, debug=False, require_wake=True):
    gate = VoskTurn(recognizer_factory(model, 24000), wake_phrase, require_wake=require_wake)
    frames = queue.Queue(maxsize=100)
    overflow = threading.Event()

    def capture(data, count, timing, status):
        if status:
            overflow.set()
        try:
            frames.put_nowait(bytes(data))
        except queue.Full:
            overflow.set()

    print(f'Listening locally. Say "{wake_phrase}" and your question. Ctrl+C exits.' if require_wake
          else 'Conversation open. Ask a follow-up; say "stop patrick" to close (or wait 15 seconds idle).', flush=True)
    with sd.RawInputStream(samplerate=24000, channels=1, dtype="int16", blocksize=480,
                           device=input_device, callback=capture):
        announced = not require_wake
        last_text = ""
        last_meter = time.monotonic()
        peak = 0
        while True:
            if overflow.is_set():
                raise TimeoutError("Microphone overrun. Discarded the recording; please try again.")
            try:
                pcm = frames.get(timeout=0.1)
            except queue.Empty:
                continue
            audio = gate.feed(pcm)
            if debug:
                peak = max(peak, pcm_level(pcm))
                if gate.last_text and gate.last_text != last_text:
                    print(f'Vosk {"final" if gate.last_final else "partial"}: {gate.last_text}', flush=True)
                    last_text = gate.last_text
                if time.monotonic() - last_meter >= 2:
                    print(f"Mic level: {peak:.4f}" + (" — very quiet; check microphone/mute" if peak < 0.001 else ""), flush=True)
                    peak = 0
                    last_meter = time.monotonic()
            if gate.active and not announced:
                print("Wake detected. Listening for the end of your sentence…", flush=True)
                announced = True
            if audio is not None:
                return audio


def listen_test(model_path, input_device=None, wake_phrase="hey patrick"):
    import sounddevice as sd
    model, recognizer_factory = load_vosk(model_path)
    print("Offline microphone/Vosk test. No audio is sent to OpenAI.")
    print("Input:", sd.query_devices(input_device, "input")["name"])
    require_wake = True
    while True:
        try:
            audio = capture_turn(sd, model, recognizer_factory, input_device, wake_phrase, debug=True, require_wake=require_wake)
            print(f"Turn detected: {len(audio) / 48000:.2f} seconds. Wake and endpoint worked.")
            require_wake = False
        except TimeoutError as exc:
            print(exc)
            require_wake = True


def load_vosk(model_path):
    if not Path(model_path).is_dir():
        raise ValueError(f"Vosk model directory not found: {model_path}. Set --vosk-model to your unpacked model.")
    try:
        from vosk import Model, KaldiRecognizer
    except ImportError:
        raise ValueError('Install Vosk: python -m pip install -e ".[realtime,audio]"') from None
    return Model(str(model_path)), KaldiRecognizer
