import io
import json
import unittest
import types
from unittest.mock import patch
from patrick.realtime import chat, configure, respond, continue_tools, voice_chat, system_instructions
from patrick.knowledge import KnowledgeBase


class Socket:
    def __init__(self, events):
        self.events = iter(events)
        self.sent = []
    def send(self, data):
        self.sent.append(json.loads(data))
    def recv(self, timeout):
        return json.dumps(next(self.events))


class RealtimeTests(unittest.TestCase):
    def test_web_and_pdf_tools_are_both_available(self):
        from patrick.tools import OpenAISearchTools
        ws = Socket([{"type": "session.updated"}])
        configure(ws, "Be concise", knowledge=KnowledgeBase("knowledge/revobots.json"),
                  search=OpenAISearchTools("test-key"))
        session = ws.sent[0]["session"]
        self.assertEqual({tool["name"] for tool in session["tools"]}, {"web_search", "knowledge_search"})
        self.assertIn("Keep private PDF details out of web queries", session["instructions"])

    def test_web_search_dispatches_and_resumes_audio(self):
        from patrick.tools import WEB_SEARCH_SCHEMA
        class Search:
            schemas = [WEB_SEARCH_SCHEMA]
            def execute(self, name, arguments, cancelled, register_stream=lambda stream: None):
                self.called = (name, json.loads(arguments))
                return {"summary": "Fresh news", "sources": [{"title": "Example", "url": "https://example.com"}]}
        search = Search()
        ws = Socket([])
        response = {"output": [{"type": "function_call", "call_id": "web1", "name": "web_search",
                                 "arguments": '{"query":"latest robotics news"}'}]}
        self.assertTrue(continue_tools(ws, response, KnowledgeBase("knowledge/revobots.json"), "audio", 0, search=search))
        self.assertEqual(search.called, ("web_search", {"query": "latest robotics news"}))
        self.assertEqual(ws.sent[0]["item"]["call_id"], "web1")
        self.assertIn("Fresh news", ws.sent[0]["item"]["output"])
        self.assertEqual(ws.sent[1]["response"]["output_modalities"], ["audio"])

    def test_web_search_failure_is_returned_to_model(self):
        class Search:
            def execute(self, *args):
                return {"error": "Web search failed or timed out. Do not claim current facts were verified."}
        ws = Socket([])
        continue_tools(ws, {"output": [{"type": "function_call", "name": "web_search", "call_id": "web1", "arguments": "{}"}]},
                       None, "text", 0, search=Search())
        self.assertIn("error", json.loads(ws.sent[0]["item"]["output"]))

    def test_default_prompt_uses_robot_identity(self):
        with patch.dict("os.environ", {"OPENAI_REALTIME_INSTRUCTIONS": "", "SYSTEM_PROMPT_FILE": "patrick/system_prompt.txt"}):
            prompt = system_instructions()
        self.assertIn("Aditya Raj", prompt)
        self.assertIn("Revobots", prompt)

    def test_followup_capture_starts_after_playback_drains(self):
        playback = []
        capture_modes = []
        class Speaker:
            def __init__(self, **kwargs): pass
            def __enter__(self):
                playback.append("playing")
                return self
            def __exit__(self, *args): playback.append("drained")
            def write(self, data): pass
        def capture(*args, **kwargs):
            capture_modes.append(kwargs["require_wake"])
            if len(capture_modes) == 1:
                return b"aa" * 3000
            self.assertEqual(playback, ["playing", "drained"])
            raise KeyboardInterrupt
        sd = types.SimpleNamespace(query_devices=lambda *args: {"name": "test"}, RawOutputStream=Speaker)
        ws = Socket([{"type": "session.updated"},
                     {"type": "response.done", "response": {"status": "completed"}}])
        with patch.dict("sys.modules", {"sounddevice": sd}), \
             patch("patrick.realtime_capture.load_vosk", return_value=(object(), object())), \
             patch("patrick.realtime_capture.capture_turn", side_effect=capture):
            with self.assertRaises(KeyboardInterrupt):
                voice_chat(ws, "Be concise")
        self.assertEqual(capture_modes, [True, False])

    def test_rag_tool_schema_is_realtime_format(self):
        kb = KnowledgeBase("knowledge/revobots.json")
        ws = Socket([{"type": "session.updated"}])
        configure(ws, "Be concise", voice=True, knowledge=kb)
        session = ws.sent[0]["session"]
        self.assertEqual(session["tools"][0]["name"], "knowledge_search")
        self.assertNotIn("function", session["tools"][0])
        self.assertIn("always call knowledge_search", session["instructions"])

    def test_pdf_index_tool_result_resumes_streamed_answer(self):
        kb = KnowledgeBase("knowledge/revobots.json")
        call = {"type": "function_call", "name": "knowledge_search", "call_id": "kb1",
                "arguments": json.dumps({"query": "Revobots cameras"})}
        ws = Socket([{"type": "response.done", "response": {"status": "completed", "output": [call]}},
                     {"type": "response.output_text.delta", "delta": "Retrieved answer"},
                     {"type": "response.done", "response": {"status": "completed"}}])
        output = io.StringIO()
        respond(ws, "Tell me about cameras", output, knowledge=kb)
        result = ws.sent[2]["item"]
        self.assertEqual(result["call_id"], "kb1")
        excerpts = json.loads(result["output"])["excerpts"]
        self.assertTrue(excerpts)
        self.assertIn(".pdf", excerpts[0]["source"])
        self.assertIn("page", excerpts[0])
        self.assertIn("Retrieved answer", output.getvalue())

    def test_rag_limits_search_rounds(self):
        with self.assertRaisesRegex(RuntimeError, "limit reached"):
            continue_tools(Socket([]), {"output": [{"type": "function_call"}]}, None, "audio", 4)

    def test_voice_session_uses_matching_pcm_and_manual_turns(self):
        ws = Socket([{"type": "session.updated"}])
        configure(ws, "Be concise", voice=True)
        session = ws.sent[0]["session"]
        self.assertEqual(session["output_modalities"], ["audio"])
        self.assertIsNone(session["audio"]["input"]["turn_detection"])
        self.assertEqual(session["audio"]["input"]["format"], session["audio"]["output"]["format"])
        self.assertEqual(session["audio"]["output"]["format"]["rate"], 24000)

    def test_stream_and_turn_events(self):
        ws = Socket([{"type": "response.output_text.delta", "delta": "Hello"},
                     {"type": "response.output_text.delta", "delta": " there"},
                     {"type": "response.done", "response": {"status": "completed"}}])
        output = io.StringIO()
        respond(ws, "Hi", output)
        self.assertEqual(output.getvalue(), "Patrick: Hello there\n")
        self.assertEqual(ws.sent[0]["item"]["content"][0]["text"], "Hi")
        self.assertEqual(ws.sent[1]["response"]["output_modalities"], ["text"])

    def test_session_configuration_and_quit(self):
        ws = Socket([{"type": "session.created"}, {"type": "session.updated"}])
        chat(ws, "Be concise", read=lambda _: "/quit", output=io.StringIO())
        self.assertEqual(len(ws.sent), 1)
        self.assertTrue(ws.sent[0]["session"]["instructions"].startswith("Be concise"))
        self.assertIn("Perform tool calls silently", ws.sent[0]["session"]["instructions"])

    def test_api_error(self):
        ws = Socket([{"type": "error", "error": {"message": "Quota exceeded"}}])
        with self.assertRaisesRegex(RuntimeError, "Quota exceeded"):
            respond(ws, "Hi", io.StringIO())

    def test_failed_response(self):
        ws = Socket([{"type": "response.done", "response": {"status": "failed"}}])
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            respond(ws, "Hi", io.StringIO())
