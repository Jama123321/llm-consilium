from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "chat_id INTEGER NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL, "
    "active INTEGER NOT NULL DEFAULT 0);"
    "CREATE TABLE IF NOT EXISTS session_settings (session_id INTEGER PRIMARY KEY, "
    "tool TEXT, mode TEXT, sensitivity TEXT, model TEXT, members TEXT, size INTEGER, "
    "show_footer INTEGER);"
    "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "session_id INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, "
    "created_at TEXT NOT NULL);"
)
_DEFAULT_TITLE = "New chat"
_SETTABLE = ("tool", "mode", "sensitivity", "model", "members", "size", "show_footer")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BotStore:
    def __init__(self, db_path, *, default_sensitivity: str = "sensitive") -> None:
        self._path = str(db_path)
        self._default_sensitivity = default_sensitivity
        try:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as c, c:
                c.executescript(_SCHEMA)
        except (sqlite3.Error, OSError):
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _default_settings_row(self) -> dict:
        return {"tool": "council", "mode": "", "sensitivity": self._default_sensitivity,
                "model": "", "members": "[]", "size": None, "show_footer": 1}

    def active_session(self, chat_id) -> int:
        try:
            with closing(self._connect()) as c:
                row = c.execute(
                    "SELECT id FROM sessions WHERE chat_id=? AND active=1", (chat_id,)
                ).fetchone()
        except (sqlite3.Error, OSError):
            return -1
        if row:
            return int(row["id"])
        return self.create_session(chat_id)

    def create_session(self, chat_id, title: str = _DEFAULT_TITLE) -> int:
        try:
            with closing(self._connect()) as c, c:
                prev = c.execute(
                    "SELECT id FROM sessions WHERE chat_id=? AND active=1", (chat_id,)
                ).fetchone()
                base = self._default_settings_row()
                if prev:
                    ps = c.execute(
                        "SELECT tool, mode, sensitivity, model, members, size, show_footer "
                        "FROM session_settings WHERE session_id=?", (int(prev["id"]),)
                    ).fetchone()
                    if ps:
                        base = {k: ps[k] for k in base}
                c.execute("UPDATE sessions SET active=0 WHERE chat_id=?", (chat_id,))
                cur = c.execute(
                    "INSERT INTO sessions (chat_id, title, created_at, active) VALUES (?,?,?,1)",
                    (chat_id, title, _now()),
                )
                sid = int(cur.lastrowid)
                c.execute(
                    "INSERT INTO session_settings "
                    "(session_id, tool, mode, sensitivity, model, members, size, show_footer) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (sid, base["tool"], base["mode"], base["sensitivity"], base["model"],
                     base["members"], base["size"], base["show_footer"]),
                )
                return sid
        except (sqlite3.Error, OSError):
            return -1

    def list_sessions(self, chat_id) -> list[dict]:
        try:
            with closing(self._connect()) as c:
                rows = c.execute(
                    "SELECT id, title, created_at, active FROM sessions "
                    "WHERE chat_id=? ORDER BY id DESC", (chat_id,)
                ).fetchall()
        except (sqlite3.Error, OSError):
            return []
        return [{"id": r["id"], "title": r["title"], "created_at": r["created_at"],
                 "active": bool(r["active"])} for r in rows]

    def switch_session(self, chat_id, session_id) -> bool:
        try:
            with closing(self._connect()) as c, c:
                row = c.execute(
                    "SELECT id FROM sessions WHERE id=? AND chat_id=?", (session_id, chat_id)
                ).fetchone()
                if not row:
                    return False
                c.execute("UPDATE sessions SET active=0 WHERE chat_id=?", (chat_id,))
                c.execute("UPDATE sessions SET active=1 WHERE id=?", (session_id,))
                return True
        except (sqlite3.Error, OSError):
            return False

    def rename_session(self, session_id, title: str) -> None:
        try:
            with closing(self._connect()) as c, c:
                c.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))
        except (sqlite3.Error, OSError):
            pass

    def delete_session(self, chat_id, session_id) -> None:
        try:
            with closing(self._connect()) as c, c:
                was = c.execute(
                    "SELECT active FROM sessions WHERE id=? AND chat_id=?", (session_id, chat_id)
                ).fetchone()
                c.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
                c.execute("DELETE FROM session_settings WHERE session_id=?", (session_id,))
                c.execute("DELETE FROM sessions WHERE id=? AND chat_id=?", (session_id, chat_id))
                if was and was["active"]:
                    nxt = c.execute(
                        "SELECT id FROM sessions WHERE chat_id=? ORDER BY id DESC LIMIT 1",
                        (chat_id,),
                    ).fetchone()
                    if nxt:
                        c.execute("UPDATE sessions SET active=1 WHERE id=?", (int(nxt["id"]),))
        except (sqlite3.Error, OSError):
            pass

    def maybe_autotitle(self, session_id, content: str) -> None:
        try:
            with closing(self._connect()) as c, c:
                row = c.execute("SELECT title FROM sessions WHERE id=?", (session_id,)).fetchone()
                if row and row["title"] in ("", _DEFAULT_TITLE):
                    c.execute("UPDATE sessions SET title=? WHERE id=?",
                              (content[:40], session_id))
        except (sqlite3.Error, OSError):
            pass

    def get_settings(self, session_id) -> dict:
        try:
            with closing(self._connect()) as c:
                row = c.execute(
                    "SELECT tool, mode, sensitivity, model, members, size, show_footer "
                    "FROM session_settings WHERE session_id=?", (session_id,)
                ).fetchone()
        except (sqlite3.Error, OSError):
            row = None
        d = self._default_settings_row()
        if row:
            d.update({k: row[k] for k in d})
        try:
            d["members"] = json.loads(d["members"] or "[]")
        except (ValueError, TypeError):
            d["members"] = []
        d["show_footer"] = bool(d["show_footer"])
        return d

    def set_setting(self, session_id, key: str, value) -> None:
        if key not in _SETTABLE:
            return
        try:
            with closing(self._connect()) as c, c:
                c.execute(
                    f"UPDATE session_settings SET {key}=? WHERE session_id=?",
                    (value, session_id),
                )
        except (sqlite3.Error, OSError):
            pass

    def set_members(self, session_id, aliases) -> None:
        self.set_setting(session_id, "members", json.dumps(list(aliases)))

    def add_message(self, session_id, role: str, content: str) -> int:
        try:
            with closing(self._connect()) as c, c:
                cur = c.execute(
                    "INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                    (session_id, role, content, _now()),
                )
                return int(cur.lastrowid)
        except (sqlite3.Error, OSError):
            return -1

    def recent_messages(self, session_id, turns: int) -> list[dict]:
        try:
            with closing(self._connect()) as c:
                rows = c.execute(
                    "SELECT role, content FROM messages WHERE session_id=? "
                    "ORDER BY id DESC LIMIT ?",
                    (session_id, max(0, turns)),
                ).fetchall()
        except (sqlite3.Error, OSError):
            return []
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
