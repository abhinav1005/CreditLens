"""SQLite implementation of `Storage`: one table, the transcript stored as JSON."""

import sqlite3
from pathlib import Path

from storage.transcripts import Transcript

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    transcript_id TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    data          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcripts_created_at ON transcripts(created_at);
"""


class SQLiteStorage:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(SCHEMA)

    def put(self, transcript: Transcript) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO transcripts VALUES (?, ?, ?)",
                (transcript.transcript_id, transcript.created_at, transcript.model_dump_json()),
            )

    def get(self, transcript_id: str) -> Transcript | None:
        row = self._conn.execute(
            "SELECT data FROM transcripts WHERE transcript_id = ?", (transcript_id,)
        ).fetchone()
        return Transcript.model_validate_json(row[0]) if row else None

    def list(
        self, start: str | None = None, end: str | None = None, limit: int = 100
    ) -> list[Transcript]:
        query, args = "SELECT data FROM transcripts WHERE 1=1", []
        if start:
            query += " AND created_at >= ?"
            args.append(start)
        if end:
            query += " AND created_at < ?"
            args.append(end)
        query += " ORDER BY created_at DESC, transcript_id LIMIT ?"
        args.append(limit)
        return [Transcript.model_validate_json(r[0]) for r in self._conn.execute(query, args)]
