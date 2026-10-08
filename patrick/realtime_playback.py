"""Bounded PCM playback worker: network event handling must never wait for sound."""
import queue
import threading
import time


class AudioPlayback:
    def __init__(self, sd, device=None, max_bytes=48000 * 60):
        self.stream = sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16", device=device)
        self.frames = queue.Queue()
        self.max_bytes = max_bytes
        self.buffered = 0
        self.lock = threading.Lock()
        self.closing = threading.Event()
        self.abort = threading.Event()
        self.error = None

    def __enter__(self):
        self.speaker = self.stream.__enter__()
        self.worker = threading.Thread(target=self.run, daemon=True, name="realtime-playback")
        self.worker.start()
        return self

    def write(self, pcm):
        if self.error:
            raise RuntimeError(f"Audio playback failed: {self.error}")
        with self.lock:
            if self.buffered + len(pcm) > self.max_bytes:
                raise RuntimeError("Audio playback fell behind; buffered audio limit reached.")
            self.buffered += len(pcm)
        self.frames.put_nowait(pcm)

    def run(self):
        try:
            while not self.abort.is_set():
                try:
                    pcm = self.frames.get(timeout=0.05)
                except queue.Empty:
                    if self.closing.is_set():
                        return
                    continue
                self.speaker.write(pcm)
                with self.lock:
                    self.buffered -= len(pcm)
        except Exception as exc:
            self.error = exc

    def __exit__(self, exc_type, exc, tb):
        self.closing.set()
        if exc_type:
            self.abort.set()
            if hasattr(self.speaker, "abort"):
                self.speaker.abort()
        deadline = time.monotonic() + 60
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
