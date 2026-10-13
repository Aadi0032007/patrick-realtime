import base64
import io
import json
import threading
import types
import unittest
from unittest.mock import patch

from patrick.realtime_stop import heard_stop, StopListener
from patrick.realtime_voice import play_response
from patrick.realtime import continue_tools, voice_chat
from patrick.realtime_capture import capture_turn, ConversationStopped
from test_realtime import Socket
from test_realtime_capture import Recognizer


class Listener:
    def __init__(self):
        self.stopped = threading.Event()
    def check(self):
        return self.stopped.is_set()


class Speaker:
    def __init__(self):
        self.writes = []
        self.aborted = False
    def write(self, data, *key): self.writes.append((data, key))
    def cancel(self): self.aborted = True
    def played_audio(self): return (('audio1', 0), 120)
    def finish(self, check): return check()


class StopTests(unittest.TestCase):
    def test_late_cancel_race_error_does_not_break_next_response(self):
        from patrick.realtime import receive
        ws = Socket([{'type': 'error', 'error': {'event_id': 'local-stop-cancel', 'code': 'response_cancel_not_active'}},
                     {'type': 'response.done', 'response': {'status': 'completed'}}])
        self.assertEqual(receive(ws)['type'], 'error')
        self.assertEqual(receive(ws)['type'], 'response.done')

    def test_only_whole_word_stop_interrupts(self):
        for text in ('hello scout', 'hey', 'another question', 'stopwatch', 'nonstop', ''):
            self.assertFalse(heard_stop(Recognizer([(False, text)]), b'aa'))
        for text in ('STOP', 'stop scout', 'please stop', 'stop patrick'):
            for final in (True, False):
                self.assertTrue(heard_stop(Recognizer([(final, text)]), b'aa'))

    def test_stop_listener_ignores_other_speech_then_aborts(self):
        aborted = threading.Event()
        class Input:
            def __init__(self, **kwargs): self.callback = kwargs['callback']
            def __enter__(self):
                for _ in range(3): self.callback(b'aa', 1, None, None)
                return self
            def abort(self): pass
            def close(self): pass
        sd = types.SimpleNamespace(RawInputStream=Input, PortAudioError=RuntimeError,
            query_devices=lambda *args: {'name': 'mic', 'default_samplerate': 24000, 'max_input_channels': 1},
            check_input_settings=lambda **kw: None)
        factory = lambda *args: Recognizer([(False, 'hi scout'), (True, 'tell me a joke'), (False, 'stop scout')])
        with StopListener(sd, object(), factory, None, on_stop=aborted.set) as listener:
            self.assertTrue(aborted.wait(1))
            self.assertTrue(listener.check())

    def test_stop_cancels_active_response_drains_stale_audio_and_truncates(self):
        listener, speaker = Listener(), Speaker()
        class WS(Socket):
            def recv(self, timeout):
                value = super().recv(timeout)
                if json.loads(value)['type'] == 'response.output_audio.delta': listener.stopped.set()
                return value
        ws = WS([{'type': 'response.created', 'response': {'id': 'r1'}},
                 {'type': 'response.output_audio.delta', 'item_id': 'audio1', 'delta': base64.b64encode(b'aa').decode()},
                 {'type': 'response.output_audio.delta', 'item_id': 'audio1', 'delta': base64.b64encode(b'bb').decode()},
                 {'type': 'response.done', 'response': {'status': 'cancelled'}}])
        self.assertTrue(play_response(ws, speaker, listener))
        self.assertTrue(speaker.aborted)
        self.assertEqual(len(speaker.writes), 1)
        self.assertEqual(ws.sent[0]['type'], 'response.cancel')
        self.assertEqual(ws.sent[0]['response_id'], 'r1')
        self.assertEqual(ws.sent[1]['audio_end_ms'], 120)
        self.assertEqual(ws.sent[-1]['type'], 'input_audio_buffer.clear')

    def test_stop_during_queued_playback_after_response_done(self):
        listener, speaker = Listener(), Speaker()
        def finish(check):
            listener.stopped.set()
            return check()
        speaker.finish = finish
        ws = Socket([{'type': 'response.done', 'response': {'status': 'completed'}}])
        self.assertTrue(play_response(ws, speaker, listener))
        self.assertNotIn('response.cancel', [e['type'] for e in ws.sent])
        self.assertEqual(ws.sent[0]['type'], 'conversation.item.truncate')

    def test_stop_during_slow_tool_does_not_resume_or_wait_for_network(self):
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        class Tools:
            def execute(self, name, arguments, cancelled):
                entered.set()
                stopped.set()
                release.wait(1)
                return {'summary': 'late result'}
        ws = Socket([])
        response = {'output': [{'type': 'function_call', 'call_id': 'c1', 'name': 'web_search', 'arguments': '{}'}]}
        try:
            self.assertFalse(continue_tools(ws, response, None, 'audio', 0, Tools(), cancelled=stopped))
            self.assertTrue(entered.is_set())
            self.assertIn('Cancelled', ws.sent[0]['item']['output'])
            self.assertEqual(len(ws.sent), 1)
        finally:
            release.set()

    def test_stop_restores_wake_only_capture(self):
        modes = []
        def capture(*args, **kw):
            modes.append((kw['require_wake'], kw['rearm']))
            if len(modes) == 1: return b'aa' * 3000
            raise KeyboardInterrupt
        listener = Listener()
        sd = types.SimpleNamespace(query_devices=lambda *args: {'name': 'test'})
        with patch.dict('sys.modules', {'sounddevice': sd}), \
             patch('patrick.realtime_capture.load_vosk', return_value=(object(), object())), \
             patch('patrick.realtime_capture.capture_turn', side_effect=capture), \
             patch('patrick.realtime.AudioPlayback'), \
             patch('patrick.realtime_stop.StopListener') as monitor, \
             patch('patrick.realtime_voice.play_response', return_value=True):
            monitor.return_value.__enter__.return_value = listener
            with self.assertRaises(KeyboardInterrupt): voice_chat(Socket([{'type': 'session.updated'}]), 'prompt', name='scout')
        self.assertEqual(modes, [(True, False), (True, True)])

    def test_wake_prints_match_even_when_question_completes_in_same_frame(self):
        class Input:
            def __init__(self, **kw): self.callback = kw['callback']
            def __enter__(self):
                self.callback(b'aa', 1, None, None)
                return self
            def __exit__(self, *args): pass
        sd = types.SimpleNamespace(RawInputStream=Input, PortAudioError=RuntimeError,
            query_devices=lambda *args: {'name': 'mic', 'default_samplerate': 24000, 'max_input_channels': 1},
            check_input_settings=lambda **kw: None)
        out = io.StringIO()
        with patch('sys.stdout', out):
            audio = capture_turn(sd, object(), lambda *args: Recognizer([(True, 'hey scout tell me a joke')]),
                                 None, None, name='scout')
        self.assertEqual(audio, b'aa')
        self.assertIn('Wake detected: "hey scout"', out.getvalue())
        self.assertNotIn('hardware:', out.getvalue())

    def test_trailing_name_after_stop_is_discarded_until_silence(self):
        class Input:
            def __init__(self, **kw): self.callback = kw['callback']
            def __enter__(self):
                # Remainder of old command, quiet, then an unwoken question and fresh greeting.
                for pcm in (b'\x00\x40' * 480, bytes(24000), b'aa', b'bb'):
                    self.callback(pcm, len(pcm) // 2, None, None)
                return self
            def __exit__(self, *args): pass
        sd = types.SimpleNamespace(RawInputStream=Input, PortAudioError=RuntimeError,
            query_devices=lambda *args: {'name': 'mic', 'default_samplerate': 24000, 'max_input_channels': 1},
            check_input_settings=lambda **kw: None)
        factory = lambda *args: Recognizer([(True, 'another question'), (True, 'hi scout tell me a joke')])
        self.assertEqual(capture_turn(sd, object(), factory, None, None, name='scout', rearm=True), b'aabb')
