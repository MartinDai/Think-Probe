import asyncio
from typing import Dict

# Dictionary mapping conversation_id to asyncio.Event
_stop_events: Dict[str, asyncio.Event] = {}

def get_stop_event(conversation_id: str) -> asyncio.Event:
    if conversation_id not in _stop_events:
        _stop_events[conversation_id] = asyncio.Event()
    return _stop_events[conversation_id]

def set_stop_event(conversation_id: str):
    if conversation_id in _stop_events:
        _stop_events[conversation_id].set()

def clear_stop_event(conversation_id: str):
    if conversation_id in _stop_events:
        del _stop_events[conversation_id]
