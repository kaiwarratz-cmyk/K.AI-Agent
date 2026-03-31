from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


class SecretStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS secrets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL,
                    value TEXT NOT NULL,
                    meta TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_secrets_alias ON secrets(alias)")

    @staticmethod
    def _norm_alias(alias: str) -> str:
        raw = str(alias or "").strip().lower()
        if not raw:
            raw = "secret"
        raw = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in raw)
        return raw[:80]

    @classmethod
    def normalize_alias(cls, alias: str) -> str:
        return cls._norm_alias(alias)

    def upsert_secret(self, alias: str, value: str, meta: Optional[Dict[str, Any]] = None) -> str:
        a = self._norm_alias(alias)
        v = str(value or "").strip()
        m = json.dumps(meta or {}, ensure_ascii=False)
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM secrets WHERE alias=? LIMIT 1", (a,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE secrets SET value=?, meta=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (v, m, int(row["id"])),
                )
            else:
                conn.execute(
                    "INSERT INTO secrets(alias, value, meta) VALUES(?,?,?)",
                    (a, v, m),
                )
        return a

    def get_secret(self, alias: str) -> Optional[Dict[str, Any]]:
        a = self._norm_alias(alias)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT alias, value, meta, created_at, updated_at FROM secrets WHERE alias=? LIMIT 1",
                (a,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["meta"] = json.loads(str(out.get("meta", "{}") or "{}"))
        except Exception:
            out["meta"] = {}
        return out

    def has_alias(self, alias: str) -> bool:
        return self.get_secret(alias) is not None

    def list_aliases(self, limit: int = 200) -> list[Dict[str, Any]]:
        take = max(1, min(int(limit or 200), 2000))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT alias, meta, created_at, updated_at FROM secrets ORDER BY updated_at DESC, alias ASC LIMIT ?",
                (take,),
            ).fetchall()
        out: list[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["meta"] = json.loads(str(item.get("meta", "{}") or "{}"))
            except Exception:
                item["meta"] = {}
            out.append(item)
        return out

    def delete_alias(self, alias: str) -> bool:
        a = self._norm_alias(alias)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM secrets WHERE alias=?", (a,))
            return int(cur.rowcount or 0) > 0

    @staticmethod
    def fingerprint(value: str) -> str:
        v = str(value or "")
        return hashlib.sha256(v.encode("utf-8")).hexdigest()[:12]
