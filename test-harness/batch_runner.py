# batch_runner.py
"""
批量跑测管线。
1. 准备隔离运行环境：runtime/decision_test.db（从真实库复制，继承分身配置）、runtime/chroma_test/
2. 用环境变量 DECISION_DB_PATH / CHROMA_DB_PATH 启动一个隔离的后端实例（默认端口 8010）
3. 逐个把场景 POST 给该实例，把完整报告与延迟写入 test_results.db
4. 支持断点续跑（已有成功运行的场景自动跳过）、失败重试、限速

用法：
    python batch_runner.py                 # 起隔离实例并跑全部未跑场景
    python batch_runner.py --limit 5       # 只跑前 5 条未跑场景
    python batch_runner.py --category fast_trivial
    python batch_runner.py --fresh         # 重置隔离环境（重新从真实库复制）后跑
    python batch_runner.py --no-start-server --url http://127.0.0.1:8010  # 连已有实例
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

import test_storage

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, "..", "decision-backend", "decision-backend"))
BACKEND_PYTHON = os.path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
REAL_DB = os.path.join(BACKEND_DIR, "decision.db")
REAL_CHROMA = os.path.join(BACKEND_DIR, "chroma_db")

RUNTIME_DIR = os.path.join(HERE, "runtime")
TEST_DB = os.path.join(RUNTIME_DIR, "decision_test.db")
TEST_CHROMA = os.path.join(RUNTIME_DIR, "chroma_test")
SERVER_LOG = os.path.join(RUNTIME_DIR, "uvicorn_test.log")

DEFAULT_PORT = 8010
REQUEST_TIMEOUT = 300  # 慢回路含多次 LLM 调用，给足超时


# ============================================================
# 隔离环境
# ============================================================
def prepare_runtime(fresh: bool = False):
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    if fresh and os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if fresh and os.path.exists(TEST_CHROMA):
        shutil.rmtree(TEST_CHROMA)

    # SQLite：用 backup API 复制（WAL 模式下安全），继承真实库的分身配置
    if not os.path.exists(TEST_DB):
        if os.path.exists(REAL_DB):
            src = sqlite3.connect(REAL_DB)
            dst = sqlite3.connect(TEST_DB)
            src.backup(dst)
            dst.close()
            src.close()
            print(f"[隔离环境] 已从真实库复制: {TEST_DB}")
        else:
            print("[隔离环境] 真实库不存在，测试实例将自建空库（含预置分身）")

    # ChromaDB：整目录复制；不存在则由测试实例自建
    if not os.path.exists(TEST_CHROMA):
        if os.path.isdir(REAL_CHROMA):
            shutil.copytree(REAL_CHROMA, TEST_CHROMA)
            print(f"[隔离环境] 已复制向量库: {TEST_CHROMA}")
        else:
            print("[隔离环境] 真实向量库不存在，测试实例将自建")


# ============================================================
# 隔离后端实例
# ============================================================
def start_isolated_server(port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["DECISION_DB_PATH"] = TEST_DB
    env["CHROMA_DB_PATH"] = TEST_CHROMA

    log_f = open(SERVER_LOG, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [BACKEND_PYTHON, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND_DIR, env=env,
        stdout=log_f, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    url = f"http://127.0.0.1:{port}"
    print(f"[隔离实例] 启动中 pid={proc.pid}  日志: {SERVER_LOG}")
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"隔离实例启动失败，退出码 {proc.returncode}，详见 {SERVER_LOG}")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as r:
                if r.status == 200:
                    print(f"[隔离实例] 就绪: {url}")
                    return proc
        except Exception:
            time.sleep(1)
    proc.kill()
    raise RuntimeError(f"隔离实例 60 秒内未就绪，详见 {SERVER_LOG}")


def stop_server(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            proc.wait(timeout=10)
            return
        except Exception:
            pass
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


# ============================================================
# HTTP 调用
# ============================================================
def http_post_json(url: str, payload: dict, timeout: int = REQUEST_TIMEOUT) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ============================================================
# 主流程
# ============================================================
def pending_scenarios(category: str | None) -> list[dict]:
    """未跑过的场景：没有任何一条 error 为空的 run 记录"""
    all_s = test_storage.get_scenarios(category=category)
    result = []
    for s in all_s:
        runs = test_storage.get_runs(scenario_id=s["id"])
        if any(r["error"] is None for r in runs):
            continue
        result.append(s)
    return result


def run_one(base_url: str, scenario: dict) -> dict:
    t0 = time.time()
    try:
        conv = http_post_json(
            f"{base_url}/api/conversations",
            {"title": f"[TEST] #{scenario['id']} {scenario['category']}"},
        )
        report = http_post_json(
            f"{base_url}/api/conversations/{conv['id']}/messages",
            {"scenario": scenario["scenario_text"]},
        )
        latency = int((time.time() - t0) * 1000)
        return {"loop_type": report.get("loop_type"),
                "report_json": json.dumps(report, ensure_ascii=False),
                "latency_ms": latency, "error": None}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        return {"loop_type": None, "report_json": None, "latency_ms": int((time.time() - t0) * 1000),
                "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"loop_type": None, "report_json": None, "latency_ms": int((time.time() - t0) * 1000),
                "error": f"{type(e).__name__}: {e}"}


def main():
    parser = argparse.ArgumentParser(description="批量把测试场景喂给隔离的后端实例")
    parser.add_argument("--url", default=None, help="已有实例地址（配合 --no-start-server）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-start-server", action="store_true", help="不启动新实例，直连 --url")
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.0, help="场景间隔秒数（限速）")
    parser.add_argument("--fresh", action="store_true", help="重置隔离环境后再跑")
    args = parser.parse_args()

    test_storage.init_test_db()
    prepare_runtime(fresh=args.fresh)

    proc = None
    if args.no_start_server:
        base_url = (args.url or f"http://127.0.0.1:{DEFAULT_PORT}").rstrip("/")
        if ":8000" in base_url:
            print("[安全拦截] 拒绝直连 8000 端口（生产端口）。请用隔离实例，避免污染真实数据。")
            sys.exit(2)
        try:
            with urllib.request.urlopen(base_url + "/api/health", timeout=5) as r:
                if r.status != 200:
                    raise RuntimeError("health 非 200")
        except Exception as e:
            print(f"[错误] 无法连接 {base_url}: {e}")
            sys.exit(2)
        print(f"[注意] 直连已有实例 {base_url}。请确认它启动时设置了 DECISION_DB_PATH/CHROMA_DB_PATH，否则会污染真实数据！")
    else:
        proc = start_isolated_server(args.port)
        base_url = f"http://127.0.0.1:{args.port}"

    todos = pending_scenarios(args.category)
    if args.limit:
        todos = todos[: args.limit]
    total = len(todos)
    print(f"\n[跑测] 待跑场景 {total} 条（断点续跑：已成功的自动跳过）")
    if total == 0:
        if proc:
            stop_server(proc)
        print("无待跑场景，结束。")
        return

    ok, fail = 0, 0
    try:
        for i, s in enumerate(todos, 1):
            print(f"\n[{i}/{total}] #{s['id']} [{s['category']}] {s['scenario_text'][:40]}...")
            result = run_one(base_url, s)
            run_id = test_storage.insert_run(
                scenario_id=s["id"], backend_url=base_url,
                loop_type=result["loop_type"], report_json=result["report_json"],
                latency_ms=result["latency_ms"], error=result["error"],
            )
            if result["error"]:
                fail += 1
                print(f"  -> 失败 (run #{run_id}): {result['error'][:200]}")
            else:
                ok += 1
                expect = s["expected_loop"]
                match = "✓" if result["loop_type"] == expect else f"✗ 预期{expect}"
                print(f"  -> {result['loop_type']}回路 {match}  耗时 {result['latency_ms']}ms  (run #{run_id})")
            if i < total and args.delay > 0:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\n[中断] 用户终止。已完成的 run 均已入库，下次运行自动续跑。")
    finally:
        if proc:
            stop_server(proc)
            print("[隔离实例] 已关闭")

    print(f"\n===== 跑测汇总: 成功 {ok} / 失败 {fail} / 共 {total} =====")


if __name__ == "__main__":
    main()
