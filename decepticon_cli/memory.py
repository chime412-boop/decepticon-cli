"""Memory - Memoria del agente con SQLite."""

from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_DIR = Path.home() / ".local" / "share" / "decepticon"
DB_FILE = DB_DIR / "memory.db"


class Memory:
    """Memoria persistente del agente."""

    def __init__(self, session_id: str | None = None):
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_FILE))
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self._init_db()

    def _init_db(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                severity TEXT NOT NULL,
                data TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        """)

    def add(self, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (self.session_id, role, content, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def get_history(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (self.session_id, limit),
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def add_finding(self, type_: str, severity: str, data: dict) -> None:
        self.conn.execute(
            "INSERT INTO findings (session_id, type, severity, data, timestamp) VALUES (?, ?, ?, ?, ?)",
            (self.session_id, type_, severity, json.dumps(data), datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def get_findings(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT type, severity, data, timestamp FROM findings WHERE session_id = ?",
            (self.session_id,),
        ).fetchall()
        return [{"type": r[0], "severity": r[1], "data": json.loads(r[2]), "timestamp": r[3]} for r in rows]

    def save_session(self) -> None:
        self.conn.close()