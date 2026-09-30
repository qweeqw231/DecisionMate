# launcher.py
"""
DecisionMate 桌面启动器（主程序 / 测试台共用）

点击桌面快捷方式后的行为：
  1. 启动服务：
       主程序 = 后端 uvicorn:8000（同时托管前端静态文件，无需单独启动前端 dev server）
       测试台 = 测试复核台 review_app:8020
  2. 服务就绪后自动打开默认浏览器
  3. 页面打开期间持续发送心跳（见各页面里的 @dm-hb 脚本）：
       关闭 / 离开页面（pagehide）→ 约 10 秒后自动停止服务并释放内存
       心跳超时（兜底，如浏览器崩溃）→ 约 115 秒后停止
  4. 直接关闭本控制台窗口或按 Ctrl+C，也会立即停止服务

用法：
    python launcher.py --mode main
    python launcher.py --mode test
    python launcher.py --mode main --no-browser    # 不自动打开浏览器（调试用）
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
BACKEND_DIR = os.path.join(REPO_ROOT, "decision-backend", "decision-backend")
TEST_DIR = os.path.join(REPO_ROOT, "test-harness")

# 用启动本脚本的解释器去启动服务（.cmd 传入的是后端 venv 的 python）
PYTHON = sys.executable

MODES = {
    "main": {
        "title": "DecisionMate 主程序",
        "cwd": BACKEND_DIR,
        "cmd": [PYTHON, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
        "url": "http://127.0.0.1:8000",
        "ready_path": "/api/health",
        "heartbeat_port": 8011,
        "show_lan": True,
    },
    "test": {
        "title": "DecisionMate 测试台",
        "cwd": TEST_DIR,
        "cmd": [PYTHON, "review_app.py", "--port", "8020"],
        "url": "http://127.0.0.1:8020",
        "ready_path": "/api/stats",
        "heartbeat_port": 8021,
        "show_lan": False,
    },
}

BYE_GRACE = 10.0      # 收到 pagehide 后再等这么久，仍无新心跳则停止（刷新页面会在几秒内补发心跳，不会误停）
BEAT_TIMEOUT = 90.0   # 普通心跳超时（后台标签页会被浏览器节流到约 60 秒/次，故必须大于 60）
STALE_EXTRA = 25.0    # 心跳超时后再给 25 秒恢复期（防系统休眠唤醒瞬间误判）


# ==========================================
# 心跳接收器（浏览器页面 -> 本窗口）
# ==========================================

class _HeartbeatHandler(BaseHTTPRequestHandler):
    """接收浏览器页面的心跳（POST /beat）与页面关闭信号（POST /bye）"""

    def _end(self, code: int = 204, body: bytes = b""):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self):
        state = self.server.dm_state
        if self.path.startswith("/beat"):
            state["last_beat"] = time.time()
        elif self.path.startswith("/bye"):
            state["last_bye"] = time.time()
        self._end()

    def do_GET(self):
        self._end(200, b"ok")

    def log_message(self, fmt, *args):
        pass


def start_heartbeat_server(port: int, state: dict):
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), _HeartbeatHandler)
    except OSError as e:
        print(f"[警告] 心跳端口 {port} 不可用（{e}），自动停止功能不可用；仍可通过关闭本窗口停止。")
        return None
    srv.dm_state = state
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ==========================================
# 工具函数
# ==========================================

def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return None


def set_console_title(title: str):
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass


def stop_proc(proc):
    """优雅停止服务进程；失败则强杀"""
    if proc is None or proc.poll() is not None:
        return
    print("正在停止服务...")
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # 触发 uvicorn 优雅退出
        else:
            proc.terminate()
        proc.wait(timeout=8)
        return
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ==========================================
# 主流程
# ==========================================

def main() -> int:
    parser = argparse.ArgumentParser(description="DecisionMate 桌面启动器")
    parser.add_argument("--mode", choices=list(MODES.keys()), required=True,
                        help="main=主程序，test=测试台")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器（调试用）")
    args = parser.parse_args()
    cfg = MODES[args.mode]

    set_console_title(cfg["title"])
    print("=" * 58)
    print(f"  {cfg['title']}")
    print("=" * 58)

    ready_url = cfg["url"] + cfg["ready_path"]

    # 已有实例在运行：不接管、不终止，直接打开浏览器
    if http_ok(ready_url, 1.5):
        print("检测到服务已在运行，直接打开浏览器。")
        print("（该实例不是本窗口启动的，关闭页面时不会被自动停止）")
        if not args.no_browser:
            webbrowser.open(cfg["url"])
        return 0

    state = {"last_beat": None, "last_bye": None}
    hb_server = start_heartbeat_server(cfg["heartbeat_port"], state)

    print("正在启动服务...")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(cfg["cmd"], cwd=cfg["cwd"], creationflags=creationflags)

    reason = "窗口关闭"
    try:
        # 等待服务就绪（最多 60 秒）
        deadline = time.time() + 60
        while time.time() < deadline:
            if proc.poll() is not None:
                print(f"[错误] 服务启动失败，退出码 {proc.returncode}，请检查上方日志。")
                return 1
            if http_ok(ready_url):
                break
            time.sleep(0.5)
        else:
            print("[错误] 服务在 60 秒内未就绪，请检查上方日志。")
            return 1

        print(f"服务已就绪：{cfg['url']}")
        if cfg.get("show_lan"):
            ip = lan_ip()
            if ip:
                print(f"局域网访问（手机/平板）：http://{ip}:8000")
        if not args.no_browser:
            webbrowser.open(cfg["url"])
        print()
        print("  - 关闭浏览器页面后，约 10 秒自动停止服务（释放内存）")
        print("  - 保持页面打开则持续运行；刷新页面不受影响")
        print("  - 关闭本窗口或按 Ctrl+C 可立即停止")
        print()

        # 监控：页面关闭 / 心跳超时 / 服务进程退出
        stale_since = None
        while True:
            if proc.poll() is not None:
                reason = f"服务进程已退出（退出码 {proc.returncode}）"
                break
            now = time.time()
            last_beat, last_bye = state["last_beat"], state["last_bye"]
            if last_beat is not None:
                # 页面关闭信号：若之后没有新心跳（刷新会补发），则停止
                if last_bye is not None and last_bye >= last_beat and now - last_bye > BYE_GRACE:
                    reason = "浏览器页面已关闭"
                    break
                # 兜底：心跳超时（浏览器崩溃等 pagehide 未触发的场景）
                if now - last_beat > BEAT_TIMEOUT:
                    if stale_since is None:
                        stale_since = now
                    elif now - stale_since > STALE_EXTRA:
                        reason = "心跳超时（页面可能已关闭）"
                        break
                else:
                    stale_since = None
            time.sleep(0.5)
    except KeyboardInterrupt:
        reason = "手动中断（Ctrl+C）"
    finally:
        stop_proc(proc)
        if hb_server is not None:
            hb_server.shutdown()

    print(f"\n服务已停止（{reason}），内存已释放。窗口即将关闭...")
    time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())