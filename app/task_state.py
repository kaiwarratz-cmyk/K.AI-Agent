"""
Task State Tracker for K.AI
Tracks the current task per dialog_key to provide context continuity across turns.
"""
import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

_ROOT_DIR = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT_DIR / "data" / "task_state.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS task_state (
    dialog_key   TEXT PRIMARY KEY,
    task_desc    TEXT NOT NULL,
    step_nr      INTEGER DEFAULT 0,
    last_tool    TEXT DEFAULT '',
    artifacts    TEXT DEFAULT '[]',
    status       TEXT DEFAULT 'active',
    final_reply  TEXT DEFAULT '',
    created_at   REAL,
    updated_at   REAL
);
"""


class TaskStateManager:
    def __init__(self, db_path: Path = _DB_PATH):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Fix 4: Persistente Connection statt per-Call _connect().
        # check_same_thread=False ist sicher, weil _lock alle Zugriffe serialisiert.
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()
        self._migrate_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Lazy-init persistente Connection (thread-safe via _lock)."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                timeout=10,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Schließt die persistente Connection sauber."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _init_db(self):
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(_CREATE_SQL)
                conn.commit()
            except Exception:
                pass

    def _migrate_db(self):
        """Add new columns if they don't exist yet (migration)."""
        new_columns = [
            ("dialogue_state", "TEXT DEFAULT 'idle'"),
            ("working_notes", "TEXT DEFAULT '[]'"),
            ("pending_question", "TEXT DEFAULT ''"),
            ("history_summary", "TEXT DEFAULT ''"),
        ]
        with self._lock:
            conn = self._get_conn()
            for col_name, col_def in new_columns:
                try:
                    conn.execute(f"ALTER TABLE task_state ADD COLUMN {col_name} {col_def}")
                    conn.commit()
                except Exception:
                    pass  # Column already exists

    def set_task(self, dialog_key: str, task_description: str) -> None:
        """Register a new task for a dialog_key (replaces any existing)."""
        if not dialog_key or not task_description:
            return
        now = time.time()
        with self._lock:
            try:
                conn = self._get_conn()
                # Zuerst bestehende Notizen laden, um sie zu erhalten
                cursor = conn.execute("SELECT working_notes FROM task_state WHERE dialog_key=?", (dialog_key,))
                row = cursor.fetchone()
                existing_notes = row[0] if row else "[]"
                
                conn.execute(
                    """INSERT OR REPLACE INTO task_state 
                       (dialog_key, task_desc, step_nr, last_tool, artifacts, 
                        status, final_reply, dialogue_state, working_notes, 
                        pending_question, created_at, updated_at)
                       VALUES (?, ?, 0, '', '[]', 'active', '', 'working', ?, '', ?, ?)""",
                    (dialog_key, task_description[:1000], existing_notes, now, now),
                )
                conn.commit()
            except Exception:
                pass

    def get_state(self, dialog_key: str) -> Optional[Dict[str, Any]]:
        """Return current task state or None."""
        if not dialog_key:
            return None
        with self._lock:
            try:
                conn = self._get_conn()
                row = conn.execute(
                    "SELECT * FROM task_state WHERE dialog_key = ?",
                    (dialog_key,),
                ).fetchone()
                if row is None:
                    return None
                d = dict(row)
                try:
                    d["artifacts"] = json.loads(d.get("artifacts") or "[]")
                except Exception:
                    d["artifacts"] = []
                return d
            except Exception:
                return None

    def update_step(
        self,
        dialog_key: str,
        step_nr: int,
        last_tool: str,
        artifacts: Optional[List[str]] = None,
    ) -> None:
        """Update progress of the current task."""
        if not dialog_key:
            return
        now = time.time()
        with self._lock:
            try:
                arts = json.dumps(artifacts or [])
                conn = self._get_conn()
                conn.execute(
                    """UPDATE task_state
                       SET step_nr=?, last_tool=?, artifacts=?, updated_at=?
                       WHERE dialog_key=? AND status='active'""",
                    (step_nr, last_tool or "", arts, now, dialog_key),
                )
                conn.commit()
            except Exception:
                pass

    def complete_task(
        self, dialog_key: str, success: bool = True, final_reply: str = ""
    ) -> None:
        """Mark the task as completed."""
        if not dialog_key:
            return
        status = "done" if success else "failed"
        now = time.time()
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    """UPDATE task_state
                       SET status=?, final_reply=?, updated_at=?
                       WHERE dialog_key=?""",
                    (status, (final_reply or "")[:2000], now, dialog_key),
                )
                conn.commit()
            except Exception:
                pass

    def clear_task(self, dialog_key: str) -> None:
        """Remove task state for this dialog_key."""
        if not dialog_key:
            return
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "DELETE FROM task_state WHERE dialog_key=?", (dialog_key,)
                )
                conn.commit()
            except Exception:
                pass

    def set_dialogue_state(self, dialog_key: str, state: str) -> None:
        """Set dialogue state: idle/working/awaiting_input/done/failed"""
        if not dialog_key:
            return
        now = time.time()
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "UPDATE task_state SET dialogue_state=?, updated_at=? WHERE dialog_key=?",
                    (state, now, dialog_key),
                )
                conn.commit()
            except Exception:
                pass

    def add_working_note(self, dialog_key: str, note: str) -> None:
        """Add a key fact to working_notes (max MAX_WORKING_NOTES, oldest dropped first).

        OPT-3: Lesen und Schreiben in einer einzigen DB-Session – atomisch.
        Fix 4: Nutzt persistente Connection statt zweier separater _connect()-Aufrufe.
        """
        if not dialog_key or not note:
            return
        truncated_note = str(note)[:200]
        with self._lock:
            try:
                from app.constants import MAX_WORKING_NOTES  # Fix 8
                conn = self._get_conn()
                cursor = conn.execute(
                    "SELECT working_notes FROM task_state WHERE dialog_key=?",
                    (dialog_key,),
                )
                row = cursor.fetchone()
                if row is None:
                    return
                notes_raw = row[0]
                try:
                    notes = json.loads(notes_raw) if isinstance(notes_raw, str) else (notes_raw or [])
                except Exception:
                    notes = []
                if not isinstance(notes, list):
                    notes = []
                notes.append(truncated_note)
                if len(notes) > MAX_WORKING_NOTES:
                    notes = notes[-MAX_WORKING_NOTES:]
                conn.execute(
                    "UPDATE task_state SET working_notes=?, updated_at=? WHERE dialog_key=?",
                    (json.dumps(notes), time.time(), dialog_key),
                )
                conn.commit()
            except Exception:
                pass

    def set_history_summary(self, dialog_key: str, summary: str) -> None:
        """Store the LLM-compressed history summary"""
        if not dialog_key:
            return
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "UPDATE task_state SET history_summary=?, updated_at=? WHERE dialog_key=?",
                    ((summary or "")[:1000], time.time(), dialog_key),
                )
                conn.commit()
            except Exception:
                pass

    def set_pending_question(self, dialog_key: str, question: str) -> None:
        """Store a question the agent asked the user"""
        if not dialog_key:
            return
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "UPDATE task_state SET pending_question=?, updated_at=? WHERE dialog_key=?",
                    ((question or "")[:500], time.time(), dialog_key),
                )
                conn.commit()
            except Exception:
                pass

    def get_working_notes(self, dialog_key: str) -> List[str]:
        """Return working notes list"""
        state = self.get_state(dialog_key)
        if not state:
            return []
        notes_raw = state.get("working_notes", "[]")
        try:
            notes = json.loads(notes_raw) if isinstance(notes_raw, str) else (notes_raw or [])
        except Exception:
            notes = []
        return notes if isinstance(notes, list) else []

    def get_artifacts(self, dialog_key: str) -> List[str]:
        """Return list of artifact paths/names for current task."""
        state = self.get_state(dialog_key)
        if not state:
            return []
        arts = state.get("artifacts", [])
        return arts if isinstance(arts, list) else []


# ── Singleton ──────────────────────────────────────────────────────────────
_task_state_manager: Optional[TaskStateManager] = None
_tsm_lock = threading.Lock()


def get_task_state_manager() -> TaskStateManager:
    global _task_state_manager
    if _task_state_manager is None:
        with _tsm_lock:
            if _task_state_manager is None:
                _task_state_manager = TaskStateManager()
    return _task_state_manager
