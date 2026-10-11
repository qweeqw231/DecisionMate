#storage.py
"""
数据库存储模块
使用 SQLite 存储对话和消息记录。
Phase 3.2 实现，Phase 3.3 将接入向量数据库。

数据库文件自动创建在项目根目录：decision.db
"""

import re
import logging
import sqlite3
import json
import os
from datetime import datetime
from typing import List, Optional

# 数据库文件路径（默认 decision.db；测试实例可通过 DECISION_DB_PATH 指向隔离副本）
DB_PATH = os.getenv(
    "DECISION_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "decision.db")
)


def _get_connection() -> sqlite3.Connection:
    """获取数据库连接（自动创建文件）。启用 WAL 提升并发读写表现。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 让查询结果可以用列名访问
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    初始化数据库表结构。
    在应用启动时调用一次，如果表已存在则跳过。
    """
    conn = _get_connection()
    cursor = conn.cursor()

    # 对话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '新对话',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_pinned INTEGER NOT NULL DEFAULT 0
        )
    """)

    # 消息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    # 决策记录表（存储每轮决策的摘要参数）
    # 注意：p/q/b/f_star 是 NOT NULL，快回路决策没有量化参数，
    # 因此用新增列 params_available 区分（0 = 快回路，参数无意义），
    # 而不是让 0 被当成「真实的 f*=0」参与统计。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            scenario TEXT NOT NULL,
            p REAL NOT NULL DEFAULT 0,
            q REAL NOT NULL DEFAULT 0,
            b REAL NOT NULL DEFAULT 0,
            f_star REAL NOT NULL DEFAULT 0,
            params_available INTEGER NOT NULL DEFAULT 1,
            scenario_type TEXT NOT NULL DEFAULT '',
            loop_type TEXT NOT NULL DEFAULT 'slow',
            feedback_type TEXT DEFAULT NULL,
            feedback_text TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
        )
    """)

        # 分身表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            risk_preference TEXT NOT NULL DEFAULT 'neutral',
            core_principle TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL DEFAULT 0.25,
            is_preset INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # 初始化三个预置分身（如果不存在）
    existing = cursor.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
    if existing == 0:
        now = datetime.now().isoformat()
        preset_personas = [
            {
                "name": "激进分身",
                "risk_preference": "aggressive",
                "core_principle": "机会优先，敢于在优质窗口下重注",
                "system_prompt": "你倾向于在胜率和赔率明确占优时建议加大投入。在估算参数时，你可以基于对机会的乐观判断，给出相对积极的 p 和 b 估算。你相信机会稍纵即逝，优质窗口值得全力出击。",
                "weight": 0.4
            },
            {
                "name": "中性分身",
                "risk_preference": "neutral",
                "core_principle": "平衡收益与风险，不追求极限",
                "system_prompt": "你严格按照凯利公式的数学结论给出建议，不做情绪化调整。你追求长期复利最优，而非单次收益最大。在估算参数时保持中立客观。",
                "weight": 0.35
            },
            {
                "name": "保守分身",
                "risk_preference": "conservative",
                "core_principle": "安全边际优先，避免清零",
                "system_prompt": "你倾向于在信息不完全或赔率不明时建议观望或做空。在估算参数时，你会谨慎评估潜在风险，对 p 和 b 的估算相对保守。你的首要原则是避免清零，生存优先于收益。",
                "weight": 0.25
            }
        ]
        for p in preset_personas:
            cursor.execute(
                "INSERT INTO personas (name, risk_preference, core_principle, system_prompt, weight, is_preset, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (p["name"], p["risk_preference"], p["core_principle"], p["system_prompt"], p["weight"], now)
            )

    # 对话分身关联表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_personas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            persona_id INTEGER NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE
        )
    """)

    # 应用设置表（P1-4：关系边界的可配置规则，同时供 L3「用户亲手调整底层参数」使用）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 执行进展表（L1 执行中校准）：每条记录一次阶段性进展 + 当次重估后的参数
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            p REAL NOT NULL,
            q REAL NOT NULL,
            b REAL NOT NULL,
            f_star REAL NOT NULL,
            adjusted_f_star REAL NOT NULL,
            verdict TEXT NOT NULL,
            advice TEXT NOT NULL DEFAULT '',
            reasoning TEXT NOT NULL DEFAULT '',
            risk_level TEXT NOT NULL DEFAULT '',
            conflict INTEGER NOT NULL DEFAULT 0,
            degraded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (decision_id) REFERENCES decision_records(id) ON DELETE CASCADE
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_execution_updates_decision ON execution_updates(decision_id)"
    )

    # 反馈接口与 L1 校准都要按 (conversation_id, message_id) 定位决策记录，
    # 此前这两个字段没有索引，每次都是全表扫描。
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_decision_records_message ON decision_records(message_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_decision_records_conversation ON decision_records(conversation_id)"
    )

    conn.commit()
    _apply_migrations(conn)
    conn.close()


# ==========================================
# 轻量 schema 迁移
#
# 此前没有任何迁移机制，加字段只能靠人工 DDL。这里用 SQLite 自带的
# PRAGMA user_version 记录版本，启动时按序补齐。
# 约定：迁移必须是**幂等**的（先探测再改），因为新库由 CREATE TABLE 直接建到最新结构，
# 不会走迁移路径，而旧库需要逐级补齐。
# ==========================================

SCHEMA_VERSION = 2


def _column_names(conn, table: str) -> List[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]


def _apply_migrations(conn) -> None:
    """把数据库补齐到 SCHEMA_VERSION。"""
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < 2:
        # v2：为快回路决策引入 params_available（0 = 无量化参数）
        if "decision_records" in [
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        ] and "params_available" not in _column_names(conn, "decision_records"):
            conn.execute(
                "ALTER TABLE decision_records "
                "ADD COLUMN params_available INTEGER NOT NULL DEFAULT 1"
            )
            conn.commit()
            logging.info("[迁移] decision_records 增加 params_available 列（v2）")

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


# ==========================================
# 应用设置（键值对，值为 JSON）
# ==========================================

def get_setting(key: str, default=None):
    """读取一项设置；不存在或无法解析时返回 default。"""
    conn = _get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return default


def set_setting(key: str, value) -> None:
    """写入/覆盖一项设置（值为 JSON 序列化后的字符串）。"""
    conn = _get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, json.dumps(value, ensure_ascii=False), now)
    )
    conn.commit()
    conn.close()


def get_setting_updated_at(key: str) -> Optional[str]:
    """读取某项设置的最近更新时间。"""
    conn = _get_connection()
    row = conn.execute("SELECT updated_at FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["updated_at"] if row else None


# ==========================================
# 对话操作
# ==========================================

def next_default_conversation_title(conn) -> str:
    """
    生成不重复的默认对话标题「对话 #N」。

    P1 修复：原实现用 COUNT(*)+1，删除过对话后编号会回退，导致出现两个
    「对话 #7」（实测侧边栏确实重名）。改为取现有「对话 #N」标题里最大的 N 再 +1。
    手动改成其他名字的对话不参与编号，因此不会阻挡编号前进。
    """
    max_index = 0
    for row in conn.execute("SELECT title FROM conversations").fetchall():
        match = re.match(r"^对话 #(\d+)$", row["title"] or "")
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"对话 #{max_index + 1}"


def create_conversation(title: Optional[str] = None) -> dict:
    """创建新对话，返回对话信息"""
    conn = _get_connection()
    now = datetime.now().isoformat()

    if not title:
        title = next_default_conversation_title(conn)

    cursor = conn.execute(
        "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, now, now)
    )
    conv_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": conv_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "is_pinned": False
    }


def get_conversations() -> List[dict]:
    """获取所有对话列表（置顶优先，按更新时间倒序）"""
    conn = _get_connection()
    rows = conn.execute("""
        SELECT c.id, c.title, c.created_at, c.updated_at, c.is_pinned,
               COUNT(m.id) as message_count
        FROM conversations c
        LEFT JOIN messages m ON c.id = m.conversation_id
        GROUP BY c.id
        ORDER BY c.is_pinned DESC, c.updated_at DESC
    """).fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"],
            "is_pinned": bool(row["is_pinned"])
        }
        for row in rows
    ]


def get_conversation(conv_id: int) -> Optional[dict]:
    """获取单个对话信息"""
    conn = _get_connection()
    row = conn.execute(
        "SELECT id, title, created_at, updated_at, is_pinned FROM conversations WHERE id = ?",
        (conv_id,)
    ).fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_pinned": bool(row["is_pinned"])
    }


def update_conversation(conv_id: int, title: Optional[str] = None, is_pinned: Optional[bool] = None) -> bool:
    """更新对话（重命名或置顶）"""
    conn = _get_connection()
    now = datetime.now().isoformat()

    if title is not None:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, conv_id)
        )
    if is_pinned is not None:
        conn.execute(
            "UPDATE conversations SET is_pinned = ?, updated_at = ? WHERE id = ?",
            (1 if is_pinned else 0, now, conv_id)
        )

    conn.commit()
    conn.close()
    return True


def delete_conversation(conv_id: int) -> bool:
    """删除单个对话及其所有消息"""
    conn = _get_connection()
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()
    return True


def clear_all_conversations() -> bool:
    """清空所有对话和消息"""
    conn = _get_connection()
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()
    return True


# ==========================================
# 消息操作
# ==========================================

def add_message(conv_id: int, role: str, content: str) -> dict:
    """
    添加一条消息到指定对话。
    role: "user" 或 "assistant"
    content: 消息内容（用户输入文本或系统输出的 JSON 字符串）
    """
    conn = _get_connection()
    now = datetime.now().isoformat()

    cursor = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, now)
    )
    msg_id = cursor.lastrowid

    # 更新对话的更新时间
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conv_id)
    )

    conn.commit()
    conn.close()

    return {
        "id": msg_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "created_at": now
    }


def get_messages(conv_id: int) -> List[dict]:
    """获取指定对话的所有消息（按时间正序）"""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, conversation_id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conv_id,)
    ).fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]

def add_decision_record(conv_id: int, msg_id: int, scenario: str,
                        p: float, q: float, b: float, f_star: float,
                        scenario_type: str, loop_type: str,
                        params_available: bool = True) -> int:
    """
    存储一条决策摘要记录，返回记录ID。

    params_available=False 用于快回路决策：它没有量化参数，p/q/b/f_star 只是
    为了满足 NOT NULL 而写的占位 0，任何按 f* 统计的地方都必须先看这个标记。
    """
    conn = _get_connection()
    now = datetime.now().isoformat()

    cursor = conn.execute(
        """INSERT INTO decision_records
           (conversation_id, message_id, scenario, p, q, b, f_star,
            params_available, scenario_type, loop_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (conv_id, msg_id, scenario, p, q, b, f_star,
         1 if params_available else 0, scenario_type, loop_type, now)
    )

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id if record_id is not None else -1

def get_decision_record(record_id: int) -> Optional[dict]:
    """获取单条决策记录"""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM decision_records WHERE id = ?", (record_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def update_feedback(record_id: int, feedback_type: str, feedback_text: Optional[str] = None):
    """更新决策记录的反馈信息"""
    conn = _get_connection()
    conn.execute(
        "UPDATE decision_records SET feedback_type = ?, feedback_text = ? WHERE id = ?",
        (feedback_type, feedback_text, record_id)
    )
    conn.commit()
    conn.close()

def update_decision_message_id(decision_id: int, message_id: int):
    """更新决策记录的消息ID"""
    conn = _get_connection()
    conn.execute("UPDATE decision_records SET message_id = ? WHERE id = ?", (message_id, decision_id))
    conn.commit()
    conn.close()


def get_decision_record_by_message(conv_id: int, msg_id: int) -> Optional[dict]:
    """
    由「对话 + 消息」定位决策记录。

    反馈接口与 L1 执行中校准都需要这一步：前端只持有 msg_id，
    而决策记录在消息落库时已绑定真实 msg_id。
    """
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM decision_records WHERE message_id = ? AND conversation_id = ?",
        (msg_id, conv_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ==========================================
# L1 执行中校准：阶段性进展与参数轨迹
# ==========================================

def add_execution_update(decision_id: int, note: str, p: float, q: float, b: float,
                         f_star: float, adjusted_f_star: float, verdict: str,
                         advice: str = "", reasoning: str = "",
                         risk_level: str = "", conflict: bool = False,
                         degraded: bool = False) -> dict:
    """记录一次阶段性进展及其重估结果，返回该条记录。"""
    conn = _get_connection()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """INSERT INTO execution_updates
           (decision_id, note, p, q, b, f_star, adjusted_f_star, verdict, advice,
            reasoning, risk_level, conflict, degraded, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (decision_id, note, p, q, b, f_star, adjusted_f_star, verdict, advice,
         reasoning, risk_level, 1 if conflict else 0, 1 if degraded else 0, now)
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": row_id, "decision_id": decision_id, "note": note,
        "p": p, "q": q, "b": b, "f_star": f_star,
        "adjusted_f_star": adjusted_f_star, "verdict": verdict, "advice": advice,
        "reasoning": reasoning, "risk_level": risk_level,
        "conflict": bool(conflict), "degraded": bool(degraded), "created_at": now,
    }


def get_execution_updates(decision_id: int) -> List[dict]:
    """按时间正序返回某条决策的全部阶段性校准记录。"""
    conn = _get_connection()
    rows = conn.execute(
        """SELECT id, decision_id, note, p, q, b, f_star, adjusted_f_star, verdict,
                  advice, reasoning, risk_level, conflict, degraded, created_at
           FROM execution_updates WHERE decision_id = ?
           ORDER BY created_at ASC, id ASC""",
        (decision_id,)
    ).fetchall()
    conn.close()
    return [
        dict(row) | {"conflict": bool(row["conflict"]), "degraded": bool(row["degraded"])}
        for row in rows
    ]


# ==========================================
# P0 修复：向量库存量清理所需的 ID 查询
# 删除对话/清空数据时必须先取出决策ID，否则 Chroma 中的向量会变成孤儿，
# 却仍被 search_similar_decisions 检索出来当作「历史参考」注入 Prompt。
# ==========================================

def get_decision_ids_for_conversation(conv_id: int) -> List[int]:
    """获取某个对话下所有决策记录的 ID"""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id FROM decision_records WHERE conversation_id = ?", (conv_id,)
    ).fetchall()
    conn.close()
    return [row["id"] for row in rows]


def get_all_decision_ids() -> List[int]:
    """获取全部决策记录的 ID"""
    conn = _get_connection()
    rows = conn.execute("SELECT id FROM decision_records").fetchall()
    conn.close()
    return [row["id"] for row in rows]


def get_decision_records_with_report() -> List[dict]:
    """
    获取全部决策记录，并联结出其对应的系统报告 JSON（messages.content）。

    L3 系统自校正需要审视历史决策的完整内容（冲突标记、风险降级、场景识别等），
    这些字段只存在于落库的报告 JSON 里，decision_records 表本身没有对应列。
    报告可能缺失（消息被删除），此时 report_json 为 None，由调用方容错处理。
    """
    conn = _get_connection()
    rows = conn.execute("""
        SELECT d.id, d.conversation_id, d.message_id, d.scenario,
               d.p, d.q, d.b, d.f_star, d.params_available, d.scenario_type, d.loop_type,
               d.feedback_type, d.feedback_text, d.created_at,
               m.content AS report_json
        FROM decision_records d
        LEFT JOIN messages m ON m.id = d.message_id
        ORDER BY d.created_at ASC, d.id ASC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ==========================================
# phase4.2 分身操作
# ==========================================

def get_personas() -> List[dict]:
    """获取所有分身列表"""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, name, risk_preference, core_principle, system_prompt, weight, is_preset, created_at FROM personas ORDER BY is_preset DESC, id ASC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_persona(persona_id: int) -> Optional[dict]:
    """获取单个分身"""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_persona(name: str, risk_preference: str, core_principle: str, system_prompt: str, weight: float) -> int:
    """创建自定义分身，返回分身ID"""
    conn = _get_connection()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO personas (name, risk_preference, core_principle, system_prompt, weight, is_preset, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
        (name, risk_preference, core_principle, system_prompt, weight, now)
    )
    persona_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return persona_id if persona_id is not None else -1


def update_persona(persona_id: int, name: Optional[str] = None, core_principle: Optional[str] = None,
                   system_prompt: Optional[str] = None, weight: Optional[float] = None) -> bool:
    """更新分身信息"""
    conn = _get_connection()
    if name is not None:
        conn.execute("UPDATE personas SET name = ? WHERE id = ?", (name, persona_id))
    if core_principle is not None:
        conn.execute("UPDATE personas SET core_principle = ? WHERE id = ?", (core_principle, persona_id))
    if system_prompt is not None:
        conn.execute("UPDATE personas SET system_prompt = ? WHERE id = ?", (system_prompt, persona_id))
    if weight is not None:
        conn.execute("UPDATE personas SET weight = ? WHERE id = ?", (weight, persona_id))
    conn.commit()
    conn.close()
    return True


def delete_persona(persona_id: int) -> bool:
    """删除自定义分身（预置分身不可删除）"""
    conn = _get_connection()
    conn.execute("DELETE FROM personas WHERE id = ? AND is_preset = 0", (persona_id,))
    conn.commit()
    conn.close()
    return True


def reset_preset_persona(persona_id: int) -> Optional[dict]:
    """重置预置分身为默认值"""
    # 预置分身的默认值映射
    defaults = {
        "aggressive": {
            "core_principle": "机会优先，敢于在优质窗口下重注",
            "system_prompt": "你倾向于在胜率和赔率明确占优时建议加大投入。在估算参数时，你可以基于对机会的乐观判断，给出相对积极的 p 和 b 估算。你相信机会稍纵即逝，优质窗口值得全力出击。",
            "weight": 0.4
        },
        "neutral": {
            "core_principle": "平衡收益与风险，不追求极限",
            "system_prompt": "你严格按照凯利公式的数学结论给出建议，不做情绪化调整。你追求长期复利最优，而非单次收益最大。在估算参数时保持中立客观。",
            "weight": 0.35
        },
        "conservative": {
            "core_principle": "安全边际优先，避免清零",
            "system_prompt": "你倾向于在信息不完全或赔率不明时建议观望或做空。在估算参数时，你会谨慎评估潜在风险，对 p 和 b 的估算相对保守。你的首要原则是避免清零，生存优先于收益。",
            "weight": 0.25
        }
    }

    persona = get_persona(persona_id)
    if not persona or not persona["is_preset"]:
        return None

    risk = persona["risk_preference"]
    default = defaults.get(risk)
    if not default:
        return None

    conn = _get_connection()
    conn.execute(
        "UPDATE personas SET core_principle = ?, system_prompt = ?, weight = ? WHERE id = ?",
        (default["core_principle"], default["system_prompt"], default["weight"], persona_id)
    )
    conn.commit()
    conn.close()
    return get_persona(persona_id)

# ==========================================
# 对话分身关联操作
# ==========================================

def get_conversation_personas(conv_id: int) -> List[int]:
    """获取指定对话激活的分身ID列表"""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT persona_id FROM conversation_personas WHERE conversation_id = ?",
        (conv_id,)
    ).fetchall()
    conn.close()
    return [row["persona_id"] for row in rows]


def save_conversation_personas(conv_id: int, persona_ids: List[int]):
    """保存指定对话激活的分身列表（先删后插）"""
    conn = _get_connection()
    conn.execute("DELETE FROM conversation_personas WHERE conversation_id = ?", (conv_id,))
    for pid in persona_ids:
        conn.execute(
            "INSERT INTO conversation_personas (conversation_id, persona_id) VALUES (?, ?)",
            (conv_id, pid)
        )
    conn.commit()
    conn.close()