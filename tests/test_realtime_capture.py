import json
import unittest

from patrick.realtime_capture import VoskTurn, pcm_level


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
        gate = VoskTurn(Recognizer([(True, "patrick"), (True, "they patrick"), (True, "hey patrickson")]))
        for _ in range(3):
            self.assertIsNone(gate.feed(b"aa"))
        self.assertFalse(gate.active)

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
        gate = VoskTurn(Recognizer([(True, "hey patrick hello"), (True, "another question")]))
        self.assertEqual(gate.feed(b"aa"), b"aa")
        self.assertIsNone(gate.feed(b"bb"))
        self.assertFalse(gate.active)
