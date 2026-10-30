# app/monitor/store.py
import sqlite3
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from typing_extensions import Self

from app.monitor.models import Dimension, MonitorEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    dimension TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    published_at TEXT,
    collected_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_events_dim_time ON events(dimension, published_at DESC);
"""

_US = "\x1f"  # ASCII 单元分隔符，避免字段拼接歧义


def _content_hash(e: MonitorEvent) -> str:
    raw = _US.join((e.dimension.value, e.title, e.url, e.content))
    return sha256(raw.encode("utf-8")).hexdigest()


class EventStore:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def save_events(self, events: list[MonitorEvent]) -> tuple[int, int]:
        added = skipped = 0
        try:
            for e in events:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO events (dimension, title, content, url, source,"
                    " published_at, collected_at, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        e.dimension.value,
                        e.title,
                        e.content,
                        e.url,
                        e.source,
                        e.published_at.isoformat() if e.published_at else None,
                        e.collected_at.isoformat(),
                        _content_hash(e),
                    ),
                )
                if cur.rowcount == 1:
                    added += 1
                else:
                    skipped += 1
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return added, skipped

    def list_events(
        self, dimension: Dimension | None = None, limit: int = 100
    ) -> list[MonitorEvent]:
        sql = (
            "SELECT dimension, title, source, content, url, published_at, collected_at"
            " FROM events"
        )
        params: list[str] = []
        if dimension is not None:
            sql += " WHERE dimension = ?"
            params.append(dimension.value)
        sql += " ORDER BY published_at IS NULL, published_at DESC, collected_at DESC LIMIT ?"
        params.append(str(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [
            MonitorEvent(
                dimension=Dimension(r[0]),
                title=r[1],
                source=r[2],
                content=r[3],
                url=r[4],
                published_at=datetime.fromisoformat(r[5]) if r[5] else None,
                collected_at=datetime.fromisoformat(r[6]),
            )
            for r in rows
        ]

    def counts_by_dimension(self) -> dict[Dimension, int]:
        """按维度统计事件数。注意：无事件的维度不会出现在返回的 dict 中。"""
        rows = self._conn.execute(
            "SELECT dimension, COUNT(*) FROM events GROUP BY dimension"
        ).fetchall()
        return {Dimension(d): n for d, n in rows}

    def count(self) -> int:
        (n,) = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return n
