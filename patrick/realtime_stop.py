"""Local stop-only listener during responses; other speech is discarded."""
import json
import queue
import threading

from .audio_format import PCMConverter, REALTIME_RATE, device_format
from .endpoint import normalize


def heard_stop(recognizer, pcm):
    final = recognizer.AcceptWaveform(pcm)
    result = json.loads(recognizer.Result() if final else recognizer.PartialResult())
    return 'stop' in normalize(result.get('text' if final else 'partial', '')).split()


class StopListener:
    def __init__(self, sd, model, recognizer_factory, device, on_stop=lambda: None):
        self.recognizer = recognizer_factory(model, REALTIME_RATE)
        self.hardware = device_format(sd, device, 'input')
        self.converter = PCMConverter(self.hardware.rate, REALTIME_RATE, self.hardware.channels, 1)
        self.frames = queue.Queue(maxsize=100)
        self.stopped = threading.Event()
        self.closing = threading.Event()
        self.error = None
        self.on_stop = on_stop
        self.stream = sd.RawInputStream(samplerate=self.hardware.rate, channels=self.hardware.channels,
            dtype='int16', blocksize=round(self.hardware.rate * 0.02), device=device, callback=self.capture)

    def capture(self, data, count, timing, status):
        try:
            self.frames.put_nowait(bytes(data))
        except queue.Full:
            self.error = RuntimeError('Stop listener microphone overrun.')

    def __enter__(self):
        self.stream.__enter__()
        self.worker = threading.Thread(target=self.run, daemon=True, name='realtime-stop')
        self.worker.start()
        return self

    def run(self):
        try:
            while not self.closing.is_set() and not self.stopped.is_set():
                try:
                    pcm = self.converter.convert(self.frames.get(timeout=0.05))
                except queue.Empty:
                    continue
                if pcm and heard_stop(self.recognizer, pcm):
                    self.stopped.set()
                    self.on_stop()
        except Exception as exc:
            self.error = exc

    def check(self):
        if self.error:
            raise RuntimeError(f'Stop listener failed: {self.error}')
        return self.stopped.is_set()

    def __exit__(self, exc_type, exc, tb):
        self.closing.set()
        try:
            self.stream.abort()
        finally:
            self.stream.close()
            self.worker.join(1)
