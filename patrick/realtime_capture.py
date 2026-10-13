"""Local Vosk wake phrase and acoustic utterance endpointing for Realtime."""
from collections import deque
import json
import queue
import threading
import math
import struct
import time
from pathlib import Path

from .endpoint import PhraseWakeDetector, normalize, wake_phrases
from .audio_format import device_format, PCMConverter, REALTIME_RATE


class VoskTurn:
    """Keep pre-roll, activate on a wake phrase, finish on Vosk's final result."""
    def __init__(self, recognizer, wake_phrase=None, rate=24000, require_wake=True, name="patrick"):
        self.recognizer = recognizer
        self.wake = PhraseWakeDetector(wake_phrase or wake_phrases(name))
        self.stop_phrase = "stop " + normalize(name)
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
        self.wake_event = None
        self.pre_roll.append(pcm)
        final = self.recognizer.AcceptWaveform(pcm)
        result = json.loads(self.recognizer.Result() if final else self.recognizer.PartialResult())
        text = normalize(result.get("text" if final else "partial", ""))
        previous_text = self.last_text
        self.last_text, self.last_final = text, final
        matched = self.wake.match(text)
        # Close locally before command audio is sent to OpenAI.
        if "stop" in text.split():
            self.reset()
            raise ConversationStopped(f'Conversation closed. Say "{self.wake.phrase}" to reopen it.')
        if not self.active:
            if not matched:
                return None
            self.active = True
            self.wake_event = matched
            self.chunks = list(self.pre_roll)
        else:
            self.chunks.append(pcm)
        self.duration += len(pcm) / (self.rate * 2)
        self.idle += len(pcm) / (self.rate * 2)
        content = self.wake.content(text)
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
            raise IdleExpired(f'15 seconds idle. Say "{self.wake.phrase}" to reopen the conversation.')
        if self.duration >= 30:
            # Never send a truncated or wake-only turn automatically.
            self.reset()
            raise TimeoutError(f'No completed question detected. Say "{self.wake.phrase}" and try again.')
        return None


def pcm_level(pcm):
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    return math.sqrt(sum(value * value for value in samples) / max(1, len(samples))) / 32768


class IdleExpired(TimeoutError):
    pass


class ConversationStopped(TimeoutError):
    """Local command that returns the voice loop to wake-only mode."""


def capture_turn(sd, model, recognizer_factory, input_device, wake_phrase, debug=False, require_wake=True, name="patrick", rearm=False):
    hardware = device_format(sd, input_device, 'input')
    converter = PCMConverter(hardware.rate, REALTIME_RATE, hardware.channels, 1)
    gate = VoskTurn(recognizer_factory(model, REALTIME_RATE), wake_phrase, require_wake=require_wake, name=name)
    frames = queue.Queue(maxsize=100)
    overflow = threading.Event()

    def capture(data, count, timing, status):
        if status:
            overflow.set()
        try:
            frames.put_nowait(bytes(data))
        except queue.Full:
            overflow.set()

    phrases = ' / '.join(gate.wake.phrases)
    print(f'Listening locally. Say {phrases} and your question. Ctrl+C exits.' if require_wake
          else f'Conversation open. Ask a follow-up; say "stop" or "{gate.stop_phrase}" to close (or wait 15 seconds idle).', flush=True)
    with sd.RawInputStream(samplerate=hardware.rate, channels=hardware.channels, dtype="int16", blocksize=round(hardware.rate * 0.02),
                           device=input_device, callback=capture):
        last_text = ""
        last_meter = time.monotonic()
        peak = 0
        quiet = 0
        while True:
            if overflow.is_set():
                raise TimeoutError("Microphone overrun. Discarded the recording; please try again.")
            try:
                pcm = converter.convert(frames.get(timeout=0.1))
            except queue.Empty:
                continue
            if not pcm:
                continue
            # Consume the remainder of "stop NAME" before accepting a fresh wake.
            if rearm:
                quiet = quiet + len(pcm) / (REALTIME_RATE * 2) if pcm_level(pcm) < 0.01 else 0
                if quiet >= 0.4:
                    gate.reset()
                    rearm = False
                continue
            audio = gate.feed(pcm)
            if gate.wake_event:
                print(f'Wake detected: "{gate.wake_event}". Listening for the end of your sentence…', flush=True)
            if debug:
                peak = max(peak, pcm_level(pcm))
                if gate.last_text and gate.last_text != last_text:
                    print(f'Vosk {"final" if gate.last_final else "partial"}: {gate.last_text}', flush=True)
                    last_text = gate.last_text
                if time.monotonic() - last_meter >= 2:
                    print(f"Mic level: {peak:.4f}" + (" — very quiet; check microphone/mute" if peak < 0.001 else ""), flush=True)
                    peak = 0
                    last_meter = time.monotonic()
            if audio is not None:
                return audio


def listen_test(model_path, input_device=None, wake_phrase=None, name="patrick"):
    import sounddevice as sd
    model, recognizer_factory = load_vosk(model_path)
    print("Offline microphone/Vosk test. No audio is sent to OpenAI.")
    print("Input:", sd.query_devices(input_device, "input")["name"])
    require_wake = True
    rearm = False
    while True:
        try:
            audio = capture_turn(sd, model, recognizer_factory, input_device, wake_phrase, debug=True, require_wake=require_wake, name=name, rearm=rearm)
            print(f"Turn detected: {len(audio) / 48000:.2f} seconds. Wake and endpoint worked.")
            require_wake = False
            rearm = False
        except TimeoutError as exc:
            print(exc)
            require_wake = True
            rearm = isinstance(exc, ConversationStopped)


def load_vosk(model_path):
    if not Path(model_path).is_dir():
        raise ValueError(f"Vosk model directory not found: {model_path}. Set --vosk-model to your unpacked model.")
    try:
        from vosk import Model, KaldiRecognizer
    except ImportError:
        raise ValueError('Install Vosk: python -m pip install -e ".[realtime,audio]"') from None
    return Model(str(model_path)), KaldiRecognizer
