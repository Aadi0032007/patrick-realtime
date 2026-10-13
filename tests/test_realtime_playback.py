import threading
import types
import unittest
from patrick.realtime_playback import AudioPlayback


def audio_device(stream):
    return types.SimpleNamespace(RawOutputStream=stream, PortAudioError=RuntimeError,
        query_devices=lambda *args: {'name': 'test', 'default_samplerate': 24000, 'max_output_channels': 2},
        check_output_settings=lambda **kwargs: None)


class PlaybackTests(unittest.TestCase):
    def test_stop_aborts_hardware_and_discards_queued_audio(self):
        entered, release = threading.Event(), threading.Event()
        played = []
        class Speaker:
            def __init__(self, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def abort(self): release.set()
            def write(self, pcm):
                entered.set()
                release.wait(1)
                played.append(pcm)
        with AudioPlayback(audio_device(Speaker)) as audio:
            audio.write(b'aa', 'one')
            self.assertTrue(entered.wait(1))
            audio.write(b'bb', 'two')
            audio.cancel()
            audio.write(b'cc', 'three')
        self.assertEqual(played, [b'aa'])
        self.assertTrue(audio.frames.empty())

    def test_enqueue_does_not_wait_for_slow_speaker_and_exit_drains(self):
        started, release = threading.Event(), threading.Event()
        played = []
        class Speaker:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): played.append("closed")
            def write(self, pcm):
                started.set()
                if not release.wait(2):
                    raise RuntimeError("Network loop failed to make progress")
                played.append(pcm)
        sd = audio_device(Speaker)
        with AudioPlayback(sd) as audio:
            audio.write(b"aa")
            self.assertTrue(started.wait(1))
            # This represents another received network event while sound is blocked.
            audio.write(b"bb")
            self.assertEqual(played, [])
            release.set()
        self.assertEqual(played, [b"aa", b"bb", "closed"])

    def test_playback_failure_propagates_and_stream_closes(self):
        closed = threading.Event()
        class Speaker:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): closed.set()
            def write(self, pcm): raise OSError("speaker disconnected")
        with self.assertRaisesRegex(RuntimeError, "speaker disconnected"):
            with AudioPlayback(audio_device(Speaker)) as audio:
                audio.write(b"aa")
        self.assertTrue(closed.is_set())

    def test_audio_buffer_is_bounded(self):
        audio = AudioPlayback(audio_device(lambda **kw: None), max_bytes=2)
        audio.write(b"aa")
        with self.assertRaisesRegex(RuntimeError, "limit reached"):
            audio.write(b"bb")
