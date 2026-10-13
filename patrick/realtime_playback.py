"""Bounded PCM playback worker: network event handling must never wait for sound."""
import queue
import threading
import time
from .audio_format import device_format, PCMConverter, REALTIME_RATE


class AudioPlayback:
    def __init__(self, sd, device=None, max_bytes=48000 * 60):
        hardware = device_format(sd, device, 'output')
        self.converter = PCMConverter(REALTIME_RATE, hardware.rate, 1, hardware.channels)
        self.stream = sd.RawOutputStream(samplerate=hardware.rate, channels=hardware.channels, dtype="int16", device=device)
        self.frames = queue.Queue()
        self.max_bytes = max_bytes
        self.buffered = 0
        self.lock = threading.Lock()
        self.closing = threading.Event()
        self.abort = threading.Event()
        self.error = None
        self.played = {}
        self.last_item = None

    def __enter__(self):
        self.speaker = self.stream.__enter__()
        self.worker = threading.Thread(target=self.run, daemon=True, name="realtime-playback")
        self.worker.start()
        return self

    def write(self, pcm, item_id=None, content_index=0):
        if self.abort.is_set():
            return
        if self.error:
            raise RuntimeError(f"Audio playback failed: {self.error}")
        with self.lock:
            if self.buffered + len(pcm) > self.max_bytes:
                raise RuntimeError("Audio playback fell behind; buffered audio limit reached.")
            self.buffered += len(pcm)
        # Small writes allow prompt hardware abort and bound the playback estimate.
        for start in range(0, len(pcm), 960):
            self.frames.put_nowait((pcm[start:start + 960], item_id, content_index))

    def cancel(self):
        self.abort.set()
        while True:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                break
        if hasattr(self, 'speaker') and hasattr(self.speaker, 'abort'):
            self.speaker.abort()

    def played_audio(self):
        with self.lock:
            key = self.last_item
            count = self.played.get(key, 0)
        latency = getattr(self.stream, 'latency', 0) or 0
        return key, max(0, int(count / 48 - latency * 1000))

    def finish(self, stopped):
        self.closing.set()
        deadline = time.monotonic() + 60
        while self.worker.is_alive():
            if stopped():
                self.cancel()
                return True
            if time.monotonic() >= deadline:
                self.cancel()
                raise RuntimeError('Audio playback did not finish in time.')
            self.worker.join(0.05)
        return stopped()

    def run(self):
        try:
            while not self.abort.is_set():
                try:
                    pcm, item_id, content_index = self.frames.get(timeout=0.05)
                except queue.Empty:
                    if self.closing.is_set():
                        return
                    continue
                converted = self.converter.convert(pcm)
                if converted:
                    self.speaker.write(converted)
                with self.lock:
                    self.buffered -= len(pcm)
                    if item_id:
                        self.last_item = (item_id, content_index)
                        self.played[self.last_item] = self.played.get(self.last_item, 0) + len(pcm)
        except Exception as exc:
            if not self.abort.is_set():
                self.error = exc

    def __exit__(self, exc_type, exc, tb):
        self.closing.set()
        if exc_type:
            self.cancel()
        deadline = time.monotonic() + (2 if self.abort.is_set() else 60)
        try:
            while self.worker.is_alive() and time.monotonic() < deadline:
                self.worker.join(0.1)
        finally:
            self.abort.set()
            if self.worker.is_alive() and hasattr(self.speaker, "abort"):
                self.speaker.abort()
            self.stream.__exit__(exc_type, exc, tb)
        if not exc_type:
            if self.worker.is_alive():
                raise RuntimeError("Audio playback did not finish in time.")
            if self.error:
                raise RuntimeError(f"Audio playback failed: {self.error}")
