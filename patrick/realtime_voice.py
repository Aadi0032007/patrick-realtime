"""Realtime response handling with local stop-only interruption."""
import base64
import json
import time


def cancelled_calls(ws, response):
    for item in response.get('output', []):
        if item.get('type') == 'function_call':
            ws.send(json.dumps({'type': 'conversation.item.create', 'item': {
                'type': 'function_call_output', 'call_id': item['call_id'],
                'output': json.dumps({'error': 'Cancelled by user stop command.'})}}))


def interrupt(ws, speaker, active, response_id, last_audio):
    speaker.cancel()
    key, end_ms = speaker.played_audio()
    # The last received item may still be entirely queued/unheard.
    key = key or last_audio
    if active:
        cancel = {'type': 'response.cancel', 'event_id': 'local-stop-cancel'}
        if response_id:
            cancel['response_id'] = response_id
        ws.send(json.dumps(cancel))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                event = json.loads(ws.recv(timeout=0.1))
            except TimeoutError:
                continue
            kind = event.get('type')
            if kind == 'error':
                error = event.get('error', {})
                if error.get('event_id') != 'local-stop-cancel' or error.get('code') != 'response_cancel_not_active':
                    raise RuntimeError(error.get('message', 'Realtime API error'))
            if kind == 'response.done':
                cancelled_calls(ws, event.get('response', {}))
                break
        else:
            raise RuntimeError('Realtime did not acknowledge stop; reconnect before continuing.')
    if key:
        ws.send(json.dumps({'type': 'conversation.item.truncate', 'item_id': key[0],
                            'content_index': key[1], 'audio_end_ms': end_ms}))
    if last_audio and last_audio != key:
        ws.send(json.dumps({'type': 'conversation.item.truncate', 'item_id': last_audio[0],
                            'content_index': last_audio[1], 'audio_end_ms': 0}))
    ws.send(json.dumps({'type': 'input_audio_buffer.clear'}))
    return True


def play_response(ws, speaker, listener, knowledge=None, search=None):
    from .realtime import receive, continue_tools
    rounds, response_id, last_audio = 0, None, None
    active = True
    deadline = time.monotonic() + 90
    while True:
        if listener.check():
            return interrupt(ws, speaker, active, response_id, last_audio)
        try:
            event = receive(ws, timeout=0.1)
        except TimeoutError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Realtime response timed out.')
            continue
        deadline = time.monotonic() + 90
        kind = event.get('type')
        if kind == 'response.created':
            response_id = event.get('response', {}).get('id')
        elif kind == 'response.output_audio.delta':
            item_id, index = event.get('item_id'), event.get('content_index', 0)
            if item_id:
                last_audio = (item_id, index)
            speaker.write(base64.b64decode(event['delta']), item_id, index)
        elif kind == 'response.output_audio_transcript.delta':
            print(event.get('delta', ''), end='', flush=True)
        elif kind == 'response.done':
            active = False
            print()
            response = event.get('response', {})
            if listener.check():
                cancelled_calls(ws, response)
                return interrupt(ws, speaker, False, response_id, last_audio)
            if response.get('status') != 'completed':
                detail = response.get('status_details') or {}
                raise RuntimeError(detail.get('error', {}).get('message', 'Audio response did not complete.'))
            if continue_tools(ws, response, knowledge, 'audio', rounds, search=search, cancelled=listener.stopped):
                rounds += 1
                active, response_id = True, None
                continue
            if speaker.finish(listener.check):
                return interrupt(ws, speaker, False, response_id, last_audio)
            return False
