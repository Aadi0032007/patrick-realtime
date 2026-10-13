"""Terminal chatbot using an OpenAI Realtime WebSocket session."""
import argparse
import base64
import json
import os
import sys
import threading
from urllib.parse import quote

from .environment import load_env
from .realtime_playback import AudioPlayback
from .identity import render_identity
from pathlib import Path


def system_instructions(name="patrick"):
    override = os.getenv("OPENAI_REALTIME_INSTRUCTIONS", "").strip()
    if override:
        return render_identity(override, name)
    path = Path(__file__).with_name("realtime_prompt.txt")
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError("System prompt file is empty.")
    return render_identity(prompt, name)


def receive(ws):
    event = json.loads(ws.recv(timeout=90))
    if event.get("type") == "error":
        raise RuntimeError(event.get("error", {}).get("message", "Realtime API error"))
    return event


def configure(ws, instructions, voice=False, knowledge=None, search=None):
    session = {"type": "realtime", "output_modalities": ["audio" if voice else "text"], "instructions": instructions}
    if knowledge or search:
        from .knowledge import KnowledgeTools
        tools = KnowledgeTools(knowledge, search) if knowledge else search
        session["tools"] = [{"type": "function", **schema["function"]} for schema in tools.schemas]
        session["tool_choice"] = "auto"
    if knowledge:
        session["instructions"] += (
            " Answer your own name and basic self-introduction directly from the prompt without tools. "
            "For other robot, company or creator facts, always call knowledge_search using focused English keywords. "
            "Read its results before deciding whether web search is needed; do not call local and web tools in parallel. "
            "If local excerpts answer the question, answer from them without web search. "
            "Combine relevant matches across all indexed sources, including supplied concepts and drafts.")
    if search:
        if any(schema["function"]["name"] == "weather_lookup" for schema in search.schemas):
            session["instructions"] += (
                " Use weather_lookup for weather, not RAG or web search. Do not assume user location. "
                "Clarify ambiguous cities and summarize only returned weather values.")
            session["instructions"] += (
                " If no city is named, call weather_lookup with an empty location to use the configured default."
                if getattr(search, 'default_city', '') else
                " If the user names no city, ask which city before looking up weather.")
        if any(schema["function"]["name"] == "revobots_site_search" for schema in search.schemas):
            session["instructions"] += (
                " Use revobots_site_search only for details still missing after local retrieval, or explicitly requested live updates.")
        if any(schema["function"]["name"] == "web_search" for schema in search.schemas):
            session["instructions"] += (
                " Use web_search for other current/uncertain public facts or explicitly requested searches. "
                "Keep private PDF details out of web queries. If search fails, acknowledge missing live information briefly.")
    if voice:
        session["audio"] = {
            "input": {"format": {"type": "audio/pcm", "rate": 24000}, "turn_detection": None,
                      "transcription": {"model": "gpt-4o-mini-transcribe"}},
            "output": {"format": {"type": "audio/pcm", "rate": 24000},
                       "voice": os.getenv("OPENAI_REALTIME_VOICE", "cedar")}}
    ws.send(json.dumps({"type": "session.update", "session": {
        **session}}))
    while receive(ws).get("type") != "session.updated":
        pass


def continue_tools(ws, response, knowledge, modality, rounds, search=None):
    calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
    if not calls:
        return False
    if rounds >= 4 or len(calls) > 8:
        raise RuntimeError("Knowledge search limit reached. Please ask a more specific question.")
    from .knowledge import KnowledgeTools
    tools = KnowledgeTools(knowledge, search) if knowledge else search
    for call in calls:
        result = tools.execute(call.get("name"), call.get("arguments", "{}"), threading.Event()) if tools else {"error": "Knowledge search unavailable"}
        from .knowledge import contact_filter, email_requested
        try:
            query = json.loads(call.get("arguments", "{}" )).get("query", "")
        except (ValueError, AttributeError):
            query = ""
        result = contact_filter(result, email_requested(query))
        if call.get("name") == "knowledge_search":
            count = len(result.get("excerpts", []))
            print(f'\nLocal RAG: {count} matching excerpts.', flush=True)
        if call.get("name") == "weather_lookup":
            print(f'\nWeather (Open-Meteo): {result.get("status", "unavailable")}.', flush=True)
        if call.get("name") in ("web_search", "revobots_site_search"):
            for source in result.get("sources", result.get("results", [])):
                print(f'\nWeb source: {source.get("title", "")} — {source.get("url", "")}', flush=True)
        ws.send(json.dumps({"type": "conversation.item.create", "item": {
            "type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result)}}))
    ws.send(json.dumps({"type": "response.create", "response": {"output_modalities": [modality]}}))
    return True


def respond(ws, text, output=sys.stdout, knowledge=None, search=None, name="patrick"):
    ws.send(json.dumps({"type": "conversation.item.create", "item": {
        "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}))
    ws.send(json.dumps({"type": "response.create", "response": {"output_modalities": ["text"]}}))
    output.write(f"{name.title()}: ")
    output.flush()
    rounds = 0
    try:
        while True:
            event = receive(ws)
            if event.get("type") == "response.output_text.delta":
                output.write(event.get("delta", ""))
                output.flush()
            elif event.get("type") == "response.done":
                response = event.get("response", {})
                if response.get("status") != "completed":
                    detail = response.get("status_details") or {}
                    raise RuntimeError(detail.get("error", {}).get("message", "Response did not complete."))
                if continue_tools(ws, response, knowledge, "text", rounds, search=search):
                    rounds += 1
                    continue
                break
    finally:
        output.write("\n")
        output.flush()


def chat(ws, instructions, read=input, output=sys.stdout, knowledge=None, search=None, name="patrick"):
    configure(ws, instructions, knowledge=knowledge, search=search)
    print("Connected. Type a message; /quit to exit. Ctrl+C stops the session.", file=output)
    while True:
        try:
            text = read("You: ").strip()
        except EOFError:
            return
        if text.lower() in ("/quit", "/exit"):
            return
        if text:
            respond(ws, text, output, knowledge=knowledge, search=search, name=name)


def voice_chat(ws, instructions, input_device=None, output_device=None,
               vosk_model="models/vosk-model", wake_phrase=None, debug=False, knowledge=None, search=None, name="patrick"):
    try:
        import sounddevice as sd
    except ImportError:
        raise ValueError('Install audio support: python -m pip install -e ".[realtime,audio]"') from None
    from .realtime_capture import capture_turn, load_vosk
    model, recognizer_factory = load_vosk(vosk_model)
    print("Input:", sd.query_devices(input_device, "input")["name"])
    print("Output:", sd.query_devices(output_device, "output")["name"])
    from .endpoint import wake_phrases
    phrases = wake_phrase or wake_phrases(name)
    phrase_text = phrases if isinstance(phrases, str) else ' / '.join(phrases)
    configure(ws, instructions + f" Wake phrases: {phrase_text}. Answer the question that follows the greeting.", voice=True, knowledge=knowledge, search=search)
    print("Connected. AI-generated voice. Use headphones to avoid echo.")
    print("Vosk detects the wake phrase and end of each utterance. Ctrl+C stops.")
    require_wake = True
    while True:
        try:
            audio = capture_turn(sd, model, recognizer_factory, input_device, phrases, debug=debug, require_wake=require_wake, name=name)
        except TimeoutError as exc:
            print(exc)
            require_wake = True
            continue
        ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
        for start in range(0, len(audio), 24000):
            ws.send(json.dumps({"type": "input_audio_buffer.append",
                                "audio": base64.b64encode(audio[start:start + 24000]).decode()}))
        ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        ws.send(json.dumps({"type": "response.create", "response": {"output_modalities": ["audio"]}}))
        print(f"{name.title()}: ", end="", flush=True)
        rounds = 0
        with AudioPlayback(sd, output_device) as speaker:
            while True:
                event = receive(ws)
                kind = event.get("type")
                if kind == "response.output_audio.delta":
                    speaker.write(base64.b64decode(event["delta"]))
                elif kind == "response.output_audio_transcript.delta":
                    print(event.get("delta", ""), end="", flush=True)
                elif kind == "response.done":
                    print()
                    response = event.get("response", {})
                    if response.get("status") != "completed":
                        detail = response.get("status_details") or {}
                        raise RuntimeError(detail.get("error", {}).get("message", "Audio response did not complete."))
                    if continue_tools(ws, response, knowledge, "audio", rounds, search=search):
                        rounds += 1
                        continue
                    break
        # Output stream closes (drains playback) before follow-up capture opens.
        require_wake = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--model", help="Override OPENAI_REALTIME_MODEL")
    parser.add_argument("--text", action="store_true", help="Use typed input and text output instead of voice")
    parser.add_argument("--input-device", type=int, help="Sounddevice microphone index")
    parser.add_argument("--output-device", type=int, help="Sounddevice speaker index")
    parser.add_argument("--vosk-model", default="models/vosk-model", help="Local Vosk model directory")
    parser.add_argument("--name", default="patrick", help="Assistant name; default patrick. Wake on hey/hi/hello, NAME or greeting + NAME; stop on the word stop.")
    wake_options = parser.add_mutually_exclusive_group()
    wake_options.add_argument("--wake-up", default=None, help="Wake name; defaults to --name. Accepts the name, hey/hi/hello, and greeting + name")
    wake_options.add_argument("--wake-phrase", default=None, help="Override all default wake words with one exact custom phrase")
    parser.add_argument("--debug-audio", action="store_true", help="Print local Vosk transcripts and microphone levels")
    parser.add_argument("--listen-test", action="store_true", help="Test microphone, wake phrase, and endpoint locally without OpenAI")
    parser.add_argument("--devices", action="store_true", help="List available audio devices and exit")
    parser.add_argument("--knowledge", default=None, help="Combined knowledge JSON index; defaults to RAG_KNOWLEDGE_FILE or knowledge/combined.json")
    args = parser.parse_args()
    from .endpoint import normalize, wake_phrases
    args.name = normalize(args.name)
    if not args.name:
        parser.error("--name must contain English letters or numbers")
    wake_name = normalize(args.wake_up) if args.wake_up is not None else args.name
    if not wake_name:
        parser.error("--wake-up must contain English letters or numbers")
    phrases = args.wake_phrase if args.wake_phrase is not None else wake_phrases(wake_name)
    if isinstance(phrases, str) and not normalize(phrases):
        parser.error("--wake-phrase cannot be empty")
    try:
        load_env(args.env_file)
        if args.devices:
            import sounddevice as sd
            print(sd.query_devices())
            return
        if args.listen_test:
            from .realtime_capture import listen_test
            listen_test(args.vosk_model, args.input_device, phrases, name=args.name)
            return
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise ValueError("Set OPENAI_API_KEY in .env or your environment.")
        try:
            from websockets.sync.client import connect
        except ImportError:
            raise ValueError('Install Realtime support with: python -m pip install -e ".[realtime]"') from None
        model = args.model or os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1")
        instructions = system_instructions(args.name)
        from .knowledge import KnowledgeBase
        knowledge_path = args.knowledge or os.getenv("RAG_KNOWLEDGE_FILE", "knowledge/combined.json")
        knowledge = KnowledgeBase(knowledge_path, name=args.name)
        from .tools import tools_from_env
        search = tools_from_env()
        from .tools import OpenAISearchTools
        if isinstance(search, OpenAISearchTools):
            from .official_search import RevobotsWebTools
            search = RevobotsWebTools(search)
        from .weather import weather_from_env
        search = weather_from_env(search)
        print(f"Local RAG: {knowledge.source} ({len(knowledge.chunks)} chunks)")
        tool_names = {schema['function']['name'] for schema in getattr(search, 'schemas', [])}
        print("Web search:", os.getenv("WEB_SEARCH_PROVIDER", "tavily") if 'web_search' in tool_names else "disabled")
        print("Weather:", "Open-Meteo" if 'weather_lookup' in tool_names else "disabled")
        print(f"Connecting to {model}…", flush=True)
        with connect("wss://api.openai.com/v1/realtime?model=" + quote(model, safe=""),
                     additional_headers={"Authorization": "Bearer " + key},
                     open_timeout=30, ping_interval=20, ping_timeout=60,
                     max_queue=128, max_size=4 * 1024 * 1024) as ws:
            if args.text:
                chat(ws, instructions, knowledge=knowledge, search=search, name=args.name)
            else:
                voice_chat(ws, instructions, args.input_device, args.output_device, args.vosk_model, phrases, args.debug_audio, knowledge=knowledge, search=search, name=args.name)
    except KeyboardInterrupt:
        print("\nPatrick stopped.")
    except Exception as exc:
        # Connection libraries may include request headers in their exception details.
        detail = str(exc)
        key = os.getenv("OPENAI_API_KEY", "")
        if key:
            detail = detail.replace(key, "[redacted]")
        parser.exit(2, f"Patrick Realtime error: {detail}\n")


if __name__ == "__main__":
    main()

