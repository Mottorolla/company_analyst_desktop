from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import CompanyFinancials


class HistoryDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                year INTEGER NOT NULL,
                period_start INTEGER,
                period_end INTEGER,
                inns TEXT NOT NULL,
                created_at TEXT NOT NULL,
                report_text TEXT NOT NULL,
                data_json TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(analyses)").fetchall()}
        if "period_start" not in columns:
            self.conn.execute("ALTER TABLE analyses ADD COLUMN period_start INTEGER")
        if "period_end" not in columns:
            self.conn.execute("ALTER TABLE analyses ADD COLUMN period_end INTEGER")
        self.conn.execute("UPDATE analyses SET period_start=year WHERE period_start IS NULL")
        self.conn.execute("UPDATE analyses SET period_end=year WHERE period_end IS NULL")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_name ON analyses(name)")
        self.conn.commit()

    def save(self, name: str, year: int, rows: list[CompanyFinancials], report_text: str) -> int:
        inns = "/".join(dict.fromkeys(r.inn for r in rows))
        years = sorted({int(r.year) for r in rows if r.year}) or [int(year)]
        period_start, period_end = years[0], years[-1]
        data_json = json.dumps([r.to_dict() for r in rows], ensure_ascii=False)
        cur = self.conn.execute(
            "INSERT INTO analyses(name, year, period_start, period_end, inns, created_at, report_text, data_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                period_end,
                period_start,
                period_end,
                inns,
                datetime.now().isoformat(timespec="seconds"),
                report_text,
                data_json,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list(self, query: str = "") -> list[dict[str, Any]]:
        if query.strip():
            q = f"%{query.strip()}%"
            rows = self.conn.execute(
                "SELECT id,name,year,period_start,period_end,inns,created_at FROM analyses "
                "WHERE name LIKE ? OR inns LIKE ? ORDER BY id DESC",
                (q, q),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id,name,year,period_start,period_end,inns,created_at FROM analyses ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, analysis_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["rows"] = [CompanyFinancials.from_dict(x) for x in json.loads(result["data_json"])]
        return result

    def delete(self, analysis_id: int) -> None:
        self.conn.execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
        self.conn.commit()
