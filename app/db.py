"""SQLite event logs + idempotency ledger. Single-node demo, not a queue."""
from __future__ import annotations
from contextlib import contextmanager
import sqlite3
import time
from pathlib import Path
from typing import Iterator


class Ledger:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS outgoing (
                idem_key TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                meta_id TEXT,
                not_before REAL NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS incoming (
                event_id TEXT PRIMARY KEY,
                event_kind TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                error_code TEXT NOT NULL,
                hint TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_outgoing(self, key: str, fingerprint: str) -> tuple[str, str | None]:
        """Atomically own a send or observe a previous send.

        A lost/uncertain request remains locked to avoid automatic duplicates.
        """
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT fingerprint,status,meta_id,not_before FROM outgoing WHERE idem_key=?", (key,)
            ).fetchone()
            if row is not None:
                if row["fingerprint"] != fingerprint:
                    return ("conflict", None)
                if row["status"] == "retryable":
                    if float(row["not_before"]) > time.time():
                        return ("cooldown", None)
                    db.execute("UPDATE outgoing SET status='in_progress',not_before=0, updated_at=CURRENT_TIMESTAMP WHERE idem_key=?", (key,))
                    return ("claimed", None)
                return (row["status"], row["meta_id"])
            db.execute("INSERT INTO outgoing(idem_key,fingerprint,status) VALUES(?,?,'in_progress')", (key, fingerprint))
            return ("claimed", None)

    def complete_outgoing(self, key: str, status: str, meta_id: str | None = None, retry_after_seconds: float = 0.0) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE outgoing SET status=?, meta_id=?,not_before=?,updated_at=CURRENT_TIMESTAMP WHERE idem_key=?",
                (status, meta_id, time.time() + max(0.0, retry_after_seconds) if status == "retryable" else 0, key),
            )

    def receive_once(self, event_id: str, kind: str) -> bool:
        with self.connection() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO incoming(event_id,event_kind) VALUES(?,?)",
                (event_id, kind),
            )
            return cursor.rowcount == 1

    def log(self, source: str, event_type: str, error_code: str, hint: str, attempt: int = 0) -> None:
        """Call ONLY with predefined safe hints; never put HTTP bodies here."""
        with self.connection() as db:
            db.execute(
                "INSERT INTO diagnostics(source,event_type,error_code,hint,attempt) VALUES(?,?,?,?,?)",
                (source, event_type, error_code, hint, attempt),
            )

    def recent_errors(self, limit: int = 20) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT source,event_type,error_code,hint,attempt,created_at FROM diagnostics ORDER BY id DESC LIMIT ?",
                (min(max(int(limit), 1), 50),),
            ).fetchall()
        return [dict(row) for row in rows]

    def error_counts(self) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT error_code,COUNT(*) AS total FROM diagnostics GROUP BY error_code ORDER BY total DESC LIMIT 20"
            ).fetchall()
        return [dict(row) for row in rows]
