import json
import unittest

from patrick.realtime_capture import VoskTurn, pcm_level, ConversationStopped


class Recognizer:
    def __init__(self, events):
        self.events = iter(events)
    def Reset(self):
        pass
    def AcceptWaveform(self, pcm):
        self.final, self.text = next(self.events)
        return self.final
    def Result(self):
        return json.dumps({"text": self.text})
    def PartialResult(self):
        return json.dumps({"partial": self.text})


class VoskTurnTests(unittest.TestCase):
    def test_all_greetings_wake_and_complete_question(self):
        for greeting in ("hey", "hi", "hello"):
            with self.subTest(greeting=greeting):
                gate = VoskTurn(Recognizer([(True, f"{greeting} patrick what time is it")]))
                self.assertEqual(gate.feed(b"aa"), b"aa")

    def test_all_greetings_alone_wait_for_question(self):
        for greeting in ("hey", "hi", "hello"):
            with self.subTest(greeting=greeting):
                gate = VoskTurn(Recognizer([(True, f"{greeting} patrick"), (True, "tell me a joke")]))
                self.assertIsNone(gate.feed(b"aa"))
                self.assertEqual(gate.feed(b"bb"), b"aabb")

    def test_custom_name_replaces_default_and_stop(self):
        gate = VoskTurn(Recognizer([(True, "patrick"), (True, "hi jarvis"),
                                   (False, "stop jarvis")]), name="jarvis")
        self.assertIsNone(gate.feed(b"aa"))
        self.assertFalse(gate.active)
        self.assertIsNone(gate.feed(b"bb"))
        self.assertTrue(gate.active)
        with self.assertRaises(ConversationStopped):
            gate.feed(b"cc")

    def test_alternate_greeting_with_stop_is_local(self):
        gate = VoskTurn(Recognizer([(True, "hello jarvis stop jarvis")]), name="jarvis")
        with self.assertRaises(ConversationStopped):
            gate.feed(b"aa")

    def test_explicit_wake_override_is_preserved(self):
        gate = VoskTurn(Recognizer([(True, "hi jarvis"), (True, "computer tell me a joke")]),
                        wake_phrase="computer", name="jarvis")
        self.assertIsNone(gate.feed(b"aa"))
        self.assertEqual(gate.feed(b"bb"), b"aabb")

    def test_stop_closes_open_conversation_and_discards_audio(self):
        gate = VoskTurn(Recognizer([(False, "stop patrick"), (True, "another question")]), require_wake=False)
        with self.assertRaises(ConversationStopped):
            gate.feed(b"aa")
        self.assertFalse(gate.active)
        self.assertEqual(gate.chunks, [])
        self.assertIsNone(gate.feed(b"bb"))

    def test_stop_after_wake_phrase(self):
        gate = VoskTurn(Recognizer([(True, "hey patrick stop patrick")]))
        with self.assertRaises(ConversationStopped):
            gate.feed(b"aa")

    def test_stop_word_anywhere_closes_locally(self):
        gate = VoskTurn(Recognizer([(True, "what does stop patrick mean")]), require_wake=False)
        with self.assertRaises(ConversationStopped):
            gate.feed(b"aa")

    def test_microphone_level(self):
        self.assertEqual(pcm_level(bytes(960)), 0)
        self.assertAlmostEqual(pcm_level(b"\x00\x40" * 480), 0.5)

    def test_ignores_background_and_preserves_preroll_for_combined_question(self):
        gate = VoskTurn(Recognizer([(True, "background conversation"),
                                   (False, "hey patrick what time is it"),
                                   (True, "hey patrick what time is it")]))
        self.assertIsNone(gate.feed(b"aa"))
        self.assertIsNone(gate.feed(b"bb"))
        self.assertTrue(gate.active)
        self.assertEqual(gate.feed(b"cc"), b"aabbcc")
        self.assertFalse(gate.active)

    def test_wake_alone_waits_for_question_final(self):
        gate = VoskTurn(Recognizer([(True, "hey patrick"), (True, ""),
                                   (False, "tell me a joke"), (True, "tell me a joke")]))
        for frame in (b"aa", b"bb", b"cc"):
            self.assertIsNone(gate.feed(frame))
        self.assertEqual(gate.feed(b"dd"), b"aabbccdd")

    def test_requires_whole_wake_phrase(self):
        gate = VoskTurn(Recognizer([(True, "patrickson"), (True, "high"), (True, "helloworld")]))
        for _ in range(3):
            self.assertIsNone(gate.feed(b"aa"))
        self.assertFalse(gate.active)

    def test_bare_words_and_names_wake_without_sending_greeting_only(self):
        for name in ('scout', 'patrick', 'jarvis'):
            for wake in ('hey', 'hi', 'hello', name, f'hey {name}', f'hi {name}', f'hello {name}', f'hey hello hi {name}'):
                with self.subTest(name=name, wake=wake):
                    gate = VoskTurn(Recognizer([(True, wake), (True, 'tell me a joke')]), name=name)
                    self.assertIsNone(gate.feed(b'aa'))
                    self.assertTrue(gate.active)
                    self.assertEqual(gate.feed(b'bb'), b'aabb')

    def test_bare_wake_with_question_returns_audio(self):
        for wake in ('hey', 'hi', 'hello', 'scout'):
            gate = VoskTurn(Recognizer([(True, wake + ' tell me a joke')]), name='scout')
            self.assertEqual(gate.feed(b'aa'), b'aa')

    def test_stop_and_stop_name_work_without_wake(self):
        for command in ('stop', 'stop scout', 'please stop', 'hey scout stop scout'):
            gate = VoskTurn(Recognizer([(False, command)]), name='scout', require_wake=False)
            with self.assertRaises(ConversationStopped):
                gate.feed(b'aa')
            self.assertFalse(gate.active)
            self.assertEqual(gate.chunks, [])

    def test_stop_is_a_whole_word(self):
        gate = VoskTurn(Recognizer([(True, 'tell me about a stopwatch')]), require_wake=False)
        self.assertEqual(gate.feed(b'aa'), b'aa')

    def test_followup_mentioning_name_is_not_lost(self):
        gate = VoskTurn(Recognizer([(True, 'tell me about scout')]), name='scout', require_wake=False)
        self.assertEqual(gate.feed(b'aa'), b'aa')

    def test_timeout_discards_incomplete_audio_and_resets(self):
        gate = VoskTurn(Recognizer([(True, "hey patrick"), (False, "")]), rate=1)
        self.assertIsNone(gate.feed(b"aa"))
        with self.assertRaisesRegex(TimeoutError, "15 seconds idle"):
            gate.feed(b"a" * 30)
        self.assertFalse(gate.active)
        self.assertEqual(gate.chunks, [])

    def test_followup_needs_no_wake_phrase(self):
        gate = VoskTurn(Recognizer([(False, "what about the cameras"),
                                   (True, "what about the cameras")]), require_wake=False)
        self.assertIsNone(gate.feed(b"aa"))
        self.assertEqual(gate.feed(b"bb"), b"aabb")

    def test_idle_followup_expires_and_returns_to_wake_only(self):
        gate = VoskTurn(Recognizer([(False, ""), (False, ""), (True, "what about cameras")]),
                        rate=1, require_wake=False)
        self.assertIsNone(gate.feed(b"a" * 14))
        with self.assertRaisesRegex(TimeoutError, "15 seconds idle"):
            gate.feed(b"a" * 16)
        self.assertFalse(gate.active)
        self.assertIsNone(gate.feed(b"aa"))

    def test_speech_resets_idle_timer(self):
        gate = VoskTurn(Recognizer([(False, ""), (False, "tell me"), (True, "tell me about revobots")]),
                        rate=1, require_wake=False)
        self.assertIsNone(gate.feed(b"a" * 20))
        self.assertIsNone(gate.feed(b"b" * 12))
        self.assertIsNotNone(gate.feed(b"cc"))

    def test_next_turn_requires_another_wake_phrase(self):
        gate = VoskTurn(Recognizer([(True, "hey patrick tell me a joke"), (True, "another question")]))
        self.assertEqual(gate.feed(b"aa"), b"aa")
        self.assertIsNone(gate.feed(b"bb"))
        self.assertFalse(gate.active)
