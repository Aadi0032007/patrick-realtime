import json
import struct
import types
import unittest
from patrick.audio_format import device_format, PCMConverter
from patrick.realtime_capture import capture_turn
from patrick.realtime_playback import AudioPlayback


class AudioFormatTests(unittest.TestCase):
    def device(self, accepted, native=48000, channels=2):
        def check(**kw):
            if (kw['samplerate'], kw['channels']) not in accepted:
                raise RuntimeError('unsupported rate or channels')
        return types.SimpleNamespace(PortAudioError=RuntimeError,
            query_devices=lambda *args: {'name': 'USB', 'default_samplerate': native,
                'max_input_channels': channels, 'max_output_channels': channels},
            check_input_settings=check, check_output_settings=check)

    def test_native_rate_and_stereo_only_output(self):
        fmt = device_format(self.device({(48000, 2)}), 0, 'output')
        self.assertEqual((fmt.rate, fmt.channels), (48000, 2))

    def test_falls_back_when_reported_default_is_unsupported(self):
        fmt = device_format(self.device({(44100, 1)}), 26, 'input')
        self.assertEqual((fmt.rate, fmt.channels), (44100, 1))

    def test_no_usable_format_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, 'No supported.*USB'):
            device_format(self.device(set()), 26, 'input')

    def test_streaming_resampling_preserves_state_and_duration(self):
        pcm = struct.pack('<48000h', *[i % 4000 for i in range(48000)])
        converter = PCMConverter(48000, 24000)
        chunks = b''.join(converter.convert(pcm[i:i + 1920]) for i in range(0, len(pcm), 1920))
        whole = PCMConverter(48000, 24000).convert(pcm)
        self.assertEqual(chunks, whole)
        self.assertAlmostEqual(len(chunks) / 2 / 24000, 1.0, places=4)

    def test_stereo_input_mixes_to_mono(self):
        pcm = struct.pack('<4h', 1000, 3000, -1000, -3000)
        converted = PCMConverter(24000, 24000, 2, 1).convert(pcm)
        self.assertEqual(struct.unpack('<2h', converted), (2000, -2000))

    def test_native_capture_sends_24khz_mono_to_vosk(self):
        sd = self.device({(48000, 1)}, channels=1)
        seen = []
        events = iter([(False, 'hi scout'), (True, 'hi scout tell me a joke')])
        class Recognizer:
            def Reset(self): pass
            def AcceptWaveform(self, pcm):
                seen.append(pcm)
                self.final, self.text = next(events)
                return self.final
            def Result(self): return json.dumps({'text': self.text})
            def PartialResult(self): return json.dumps({'partial': self.text})
        test = self
        class Input:
            def __init__(self, **kw):
                test.assertEqual(kw['samplerate'], 48000)
                test.assertEqual(kw['blocksize'], 960)
                self.callback = kw['callback']
            def __enter__(self):
                for _ in range(2): self.callback(struct.pack('<h', 1000) * 960, 960, None, False)
                return self
            def __exit__(self, *args): pass
        def factory(model, rate):
            self.assertEqual(rate, 24000)
            return Recognizer()
        sd.RawInputStream = Input
        audio = capture_turn(sd, object(), factory, 26, None, name='scout')
        self.assertEqual([len(p) for p in seen], [960, 960])
        self.assertEqual(len(audio), 1920)

    def test_native_playback_resamples_and_duplicates_channels(self):
        sd = self.device({(48000, 2)})
        played = []
        test = self
        class Output:
            def __init__(self, **kw):
                test.assertEqual((kw['samplerate'], kw['channels']), (48000, 2))
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def write(self, pcm): played.append(pcm)
        sd.RawOutputStream = Output
        with AudioPlayback(sd, 0) as speaker:
            speaker.write(struct.pack('<h', 2000) * 2400)
        converted = b''.join(played)
        self.assertAlmostEqual(len(converted) / 4 / 48000, 0.1, places=4)
        samples = struct.unpack('<' + 'h' * (len(converted) // 2), converted)
        self.assertTrue(all(value == 2000 for value in samples))

    def test_24khz_mono_passes_through_unchanged(self):
        pcm = struct.pack('<3h', 100, -100, 32767)
        self.assertEqual(PCMConverter(24000, 24000).convert(pcm), pcm)
