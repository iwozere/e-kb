"""In-memory conversation history for /ask multi-turn sessions.

Each user gets up to MAX_TURNS exchange pairs (user + assistant messages).
History auto-clears after TIMEOUT_SECONDS of inactivity, so a new /ask
question after a gap starts a fresh conversation.

This is intentionally in-memory (not persisted) — conversation context is
ephemeral scaffolding, not knowledge worth archiving.  The knowledge base
entries themselves are the permanent record.
"""
import asyncio
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 900  # 15 minutes
MAX_TURNS = 5  # keep last 5 exchanges = 10 messages

_conversations: Dict[int, List[dict]] = {}
_timers: Dict[int, asyncio.TimerHandle] = {}


def get_history(user_id: int) -> List[dict]:
    """Return a copy of the current conversation history for this user."""
    return list(_conversations.get(user_id, []))


def add_turn(user_id: int, user_msg: str, assistant_msg: str) -> None:
    """Append a question/answer pair and reset the inactivity timer."""
    history = _conversations.setdefault(user_id, [])
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    # Trim to MAX_TURNS exchanges (2 * MAX_TURNS messages)
    max_msgs = MAX_TURNS * 2
    if len(history) > max_msgs:
        _conversations[user_id] = history[-max_msgs:]
    _reset_timer(user_id)


def clear_history(user_id: int) -> None:
    """Manually clear history (e.g. user types /ask without a question)."""
    _conversations.pop(user_id, None)
    _cancel_timer(user_id)
    logger.debug("Cleared conversation history for user %s", user_id)


def _reset_timer(user_id: int) -> None:
    _cancel_timer(user_id)
    try:
        loop = asyncio.get_running_loop()
        _timers[user_id] = loop.call_later(
            TIMEOUT_SECONDS, _expire_conversation, user_id
        )
    except RuntimeError:
        pass  # no running loop during tests


def _cancel_timer(user_id: int) -> None:
    handle = _timers.pop(user_id, None)
    if handle:
        handle.cancel()


def _expire_conversation(user_id: int) -> None:
    _conversations.pop(user_id, None)
    _timers.pop(user_id, None)
    logger.debug("Conversation expired for user %s", user_id)
