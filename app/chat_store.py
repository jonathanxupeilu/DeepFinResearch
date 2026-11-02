# app/chat_store.py
"""历史对话存储：问答会话以 JSON 单文件持久化，供 advisor 页「历史对话」面板续聊。"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

_TITLE_MAX = 24


def _derive_title(messages: list[ChatMessage]) -> str:
    first = next((m.content for m in messages if m.role == "user"), "")
    flat = " ".join(first.split())
    if len(flat) > _TITLE_MAX:
        return flat[: _TITLE_MAX - 1] + "…"
    return flat


class ChatStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def list_sessions(self) -> list[ChatSession]:
        return sorted(self._load(), key=lambda s: s.updated_at, reverse=True)

    def get(self, session_id: str) -> ChatSession | None:
        for session in self._load():
            if session.id == session_id:
                return session
        return None

    def upsert_messages(self, session_id: str, messages: list[ChatMessage]) -> None:
        sessions = self._load()
        now = datetime.now(timezone.utc)
        for i, session in enumerate(sessions):
            if session.id == session_id:
                sessions[i] = session.model_copy(
                    update={
                        "messages": messages,
                        "updated_at": now,
                        "title": _derive_title(messages) or session.title,
                    }
                )
                break
        else:
            sessions.append(
                ChatSession(
                    id=session_id,
                    title=_derive_title(messages),
                    created_at=now,
                    updated_at=now,
                    messages=messages,
                )
            )
        self._save(sessions)

    def _load(self) -> list[ChatSession]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [ChatSession.model_validate(item) for item in raw]
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning("历史对话文件读取失败，按空历史处理: %s", e)
            return []

    def _save(self, sessions: list[ChatSession]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [s.model_dump(mode="json") for s in sessions], ensure_ascii=False, indent=2
        )
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._path)
