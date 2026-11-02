# tests/unit/test_chat_store.py
"""历史对话存储：JSON 单文件持久化，upsert/排序/重载语义。"""

from app.chat_store import ChatStore
from app.models import ChatMessage


def _msgs(*pairs: tuple[str, str]) -> list[ChatMessage]:
    return [ChatMessage(role=r, content=c) for r, c in pairs]  # type: ignore[arg-type]


def test_upsert_creates_session_with_title_from_first_question(tmp_path):
    store = ChatStore(tmp_path / "chat.json")
    store.upsert_messages(
        "s1", _msgs(("user", "什么是护城河？"), ("assistant", "护城河是……"))
    )
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == "s1"
    assert sessions[0].title == "什么是护城河？"
    assert len(sessions[0].messages) == 2


def test_upsert_same_id_updates_instead_of_duplicate(tmp_path):
    store = ChatStore(tmp_path / "chat.json")
    store.upsert_messages("s1", _msgs(("user", "q1")))
    store.upsert_messages(
        "s1", _msgs(("user", "q1"), ("assistant", "a1"), ("user", "q2"))
    )
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert [m.content for m in sessions[0].messages] == ["q1", "a1", "q2"]


def test_list_sorted_by_updated_at_desc(tmp_path):
    store = ChatStore(tmp_path / "chat.json")
    store.upsert_messages("old", _msgs(("user", "旧问题")))
    store.upsert_messages("new", _msgs(("user", "新问题")))
    store.upsert_messages("old", _msgs(("user", "旧问题"), ("assistant", "追加回答")))
    assert [s.id for s in store.list_sessions()] == ["old", "new"]


def test_reload_from_disk(tmp_path):
    path = tmp_path / "chat.json"
    ChatStore(path).upsert_messages("s1", _msgs(("user", "q")))
    sessions = ChatStore(path).list_sessions()
    assert sessions[0].messages[0].content == "q"


def test_get_missing_returns_none(tmp_path):
    assert ChatStore(tmp_path / "chat.json").get("nope") is None


def test_long_title_truncated(tmp_path):
    store = ChatStore(tmp_path / "chat.json")
    store.upsert_messages("s1", _msgs(("user", "x" * 50)))
    title = store.list_sessions()[0].title
    assert len(title) <= 24
    assert title.endswith("…")
