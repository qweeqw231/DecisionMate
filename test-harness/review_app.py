# review_app.py
"""
人工复核 Web 页面。
启动后浏览器打开 http://127.0.0.1:8020 即可逐条查看场景与系统报告，标记 好/差/存疑 并写评语。

用法：
    python review_app.py            # 默认 8020 端口
    python review_app.py --port 9000
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

import test_storage

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="DecisionMate 测试复核台")


class ReviewPatch(BaseModel):
    status: str            # pending / good / bad / doubt
    comment: Optional[str] = None


def _list_query(category, review_status, loop_mismatch, q):
    where, params = ["1=1"], []
    if category:
        where.append("s.category = ?")
        params.append(category)
    if review_status:
        where.append("s.review_status = ?")
        params.append(review_status)
    if loop_mismatch:
        where.append("r.loop_type IS NOT NULL AND r.loop_type != s.expected_loop")
    if q:
        where.append("s.scenario_text LIKE ?")
        params.append(f"%{q}%")
    return f"""
        SELECT s.*, r.loop_type AS run_loop_type, r.latency_ms, r.error AS run_error, r.created_at AS run_at
        FROM scenarios s
        LEFT JOIN runs r ON r.id = (SELECT MAX(id) FROM runs WHERE scenario_id = s.id)
        WHERE {' AND '.join(where)}
        ORDER BY s.id
    """, params


@app.get("/api/scenarios")
def api_list(category: Optional[str] = None, review_status: Optional[str] = None,
             loop_mismatch: bool = False, q: Optional[str] = None):
    sql, params = _list_query(category, review_status, loop_mismatch, q)
    conn = sqlite3.connect(test_storage.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


@app.get("/api/scenarios/{scenario_id}")
def api_detail(scenario_id: int):
    s = test_storage.get_scenario(scenario_id)
    if not s:
        raise HTTPException(404, "场景不存在")
    run = test_storage.get_run_for_scenario(scenario_id)
    report = None
    if run and run.get("report_json"):
        try:
            report = json.loads(run["report_json"])
        except Exception:
            report = None
    return {**s, "run": run, "report": report}


@app.patch("/api/scenarios/{scenario_id}/review")
def api_review(scenario_id: int, body: ReviewPatch):
    if body.status not in ("pending", "good", "bad", "doubt"):
        raise HTTPException(400, "status 必须是 pending/good/bad/doubt")
    if not test_storage.get_scenario(scenario_id):
        raise HTTPException(404, "场景不存在")
    test_storage.update_review(scenario_id, body.status, body.comment)
    return {"status": "ok"}


@app.get("/api/stats")
def api_stats():
    conn = sqlite3.connect(test_storage.DB_PATH)
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) c FROM scenarios").fetchone()["c"]
    review = {r["review_status"]: r["c"] for r in conn.execute(
        "SELECT review_status, COUNT(*) c FROM scenarios GROUP BY review_status")}
    by_cat = [dict(r) for r in conn.execute(
        "SELECT category, COUNT(*) c FROM scenarios GROUP BY category ORDER BY c DESC")]
    ran = conn.execute(
        "SELECT COUNT(DISTINCT scenario_id) c FROM runs WHERE error IS NULL").fetchone()["c"]
    mismatch = conn.execute("""
        SELECT COUNT(*) c FROM scenarios s
        JOIN runs r ON r.id = (SELECT MAX(id) FROM runs WHERE scenario_id = s.id)
        WHERE r.error IS NULL AND r.loop_type != s.expected_loop
    """).fetchone()["c"]
    avg_lat = conn.execute(
        "SELECT AVG(latency_ms) a FROM runs WHERE error IS NULL").fetchone()["a"]
    conn.close()
    return {"total": total, "ran": ran, "review": review, "by_category": by_cat,
            "loop_mismatch": mismatch, "avg_latency_ms": round(avg_lat or 0)}


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "review.html"))


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    test_storage.init_test_db()
    uvicorn.run(app, host="127.0.0.1", port=args.port)
