import threading
import types
import unittest
from patrick.realtime_playback import AudioPlayback


class PlaybackTests(unittest.TestCase):
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
        sd = types.SimpleNamespace(RawOutputStream=Speaker)
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
            with AudioPlayback(types.SimpleNamespace(RawOutputStream=Speaker)) as audio:
                audio.write(b"aa")
        self.assertTrue(closed.is_set())

    def test_audio_buffer_is_bounded(self):
        audio = AudioPlayback(types.SimpleNamespace(RawOutputStream=lambda **kw: None), max_bytes=2)
        audio.write(b"aa")
        with self.assertRaisesRegex(RuntimeError, "limit reached"):
            audio.write(b"bb")
