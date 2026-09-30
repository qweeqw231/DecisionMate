# test_storage.py
"""
测试 harness 独立数据库管理。
默认 test_results.db 放在本目录下，与主系统完全隔离。
"""
from __future__ import annotations

import sqlite3
import os
from datetime import datetime
from typing import List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_test_db():
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL DEFAULT '',
            scenario_text TEXT NOT NULL,
            expected_loop TEXT NOT NULL DEFAULT 'slow',
            source TEXT NOT NULL DEFAULT 'generated',
            review_status TEXT NOT NULL DEFAULT 'pending',
            review_comment TEXT DEFAULT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER NOT NULL,
            backend_url TEXT NOT NULL,
            loop_type TEXT DEFAULT NULL,
            report_json TEXT DEFAULT NULL,
            latency_ms INTEGER DEFAULT NULL,
            error TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
        )
    """)

    # 常用查询索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_category ON scenarios(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_review ON scenarios(review_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id)")

    conn.commit()
    conn.close()


def insert_scenario(category: str, subcategory: str, scenario_text: str,
                    expected_loop: str = "slow", source: str = "generated") -> int:
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO scenarios (category, subcategory, scenario_text, expected_loop, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (category, subcategory, scenario_text, expected_loop, source, datetime.now().isoformat())
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_scenarios(category: Optional[str] = None, review_status: Optional[str] = None,
                  limit: Optional[int] = None, offset: int = 0) -> List[dict]:
    conn = _get_connection()
    where = ["1=1"]
    params = []
    if category:
        where.append("category = ?")
        params.append(category)
    if review_status:
        where.append("review_status = ?")
        params.append(review_status)
    sql = f"SELECT * FROM scenarios WHERE {' AND '.join(where)} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_scenario(scenario_id: int) -> Optional[dict]:
    conn = _get_connection()
    row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_review(scenario_id: int, status: str, comment: Optional[str] = None):
    assert status in ("pending", "good", "bad", "doubt")
    conn = _get_connection()
    conn.execute(
        "UPDATE scenarios SET review_status = ?, review_comment = ? WHERE id = ?",
        (status, comment, scenario_id)
    )
    conn.commit()
    conn.close()


def insert_run(scenario_id: int, backend_url: str, loop_type: Optional[str] = None,
               report_json: Optional[str] = None, latency_ms: Optional[int] = None,
               error: Optional[str] = None) -> int:
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO runs (scenario_id, backend_url, loop_type, report_json, latency_ms, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (scenario_id, backend_url, loop_type, report_json, latency_ms, error, datetime.now().isoformat())
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_runs(scenario_id: Optional[int] = None) -> List[dict]:
    conn = _get_connection()
    if scenario_id is not None:
        rows = conn.execute("SELECT * FROM runs WHERE scenario_id = ? ORDER BY id", (scenario_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run_for_scenario(scenario_id: int) -> Optional[dict]:
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM runs WHERE scenario_id = ? ORDER BY id DESC LIMIT 1", (scenario_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_review_stats() -> dict:
    conn = _get_connection()
    total = conn.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]
    stats = dict(conn.execute(
        "SELECT review_status, COUNT(*) FROM scenarios GROUP BY review_status"
    ).fetchall())
    conn.close()
    return {"total": total, **stats}


def clear_all_scenarios():
    conn = _get_connection()
    conn.execute("DELETE FROM scenarios")
    conn.execute("DELETE FROM runs")
    conn.commit()
    conn.close()
