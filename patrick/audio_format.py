"""Hardware audio formats and continuous PCM conversion at device boundaries."""
from dataclasses import dataclass
import math

REALTIME_RATE = 24000


@dataclass(frozen=True)
class DeviceFormat:
    rate: int
    channels: int


def device_format(sd, device, kind):
    info = sd.query_devices(device, kind)
    max_channels = int(info[f"max_{kind}_channels"])
    if max_channels < 1:
        raise ValueError(f"Not an {kind} device: {info['name']}")
    native = float(info['default_samplerate'])
    rates = [int(round(native))] if math.isfinite(native) and native > 0 else []
    rates += [REALTIME_RATE, 48000, 44100, 32000, 16000, 8000]
    check = sd.check_input_settings if kind == 'input' else sd.check_output_settings
    failures = []
    for rate in dict.fromkeys(rates):
        for channels in range(1, min(2, max_channels) + 1):
            try:
                check(device=device, samplerate=rate, channels=channels, dtype='int16')
            except sd.PortAudioError as exc:
                failures.append(str(exc))
                continue
            return DeviceFormat(rate, channels)
    raise ValueError(f"No supported mono/stereo int16 {kind} format for {info['name']}: {failures[-1]}")


class PCMConverter:
    """Convert int16 mono/stereo PCM, retaining resampling state between blocks."""
    def __init__(self, input_rate, output_rate, input_channels=1, output_channels=1):
        if input_rate <= 0 or output_rate <= 0 or input_channels not in (1, 2) or output_channels not in (1, 2):
            raise ValueError('PCM conversion needs positive rates and mono/stereo channels.')
        self.input_rate, self.output_rate = input_rate, output_rate
        self.input_channels, self.output_channels = input_channels, output_channels
        self.state = None
        self.audioop = None
        if input_rate != output_rate or input_channels != output_channels:
            try:
                import audioop
            except ImportError:
                raise ValueError('Audio resampling requires audioop; on Python 3.13+ install audioop-lts.') from None
            self.audioop = audioop

    def convert(self, pcm):
        if len(pcm) % (2 * self.input_channels):
            raise ValueError('Incomplete int16 PCM frame.')
        if not pcm or self.audioop is None:
            return pcm
        channels = self.input_channels
        if channels == 2 and self.output_channels == 1:
            pcm = self.audioop.tomono(pcm, 2, 0.5, 0.5)
            channels = 1
        if self.input_rate != self.output_rate:
            pcm, self.state = self.audioop.ratecv(pcm, 2, channels, self.input_rate, self.output_rate, self.state)
        if channels == 1 and self.output_channels == 2:
            pcm = self.audioop.tostereo(pcm, 2, 1.0, 1.0)
        return pcm
