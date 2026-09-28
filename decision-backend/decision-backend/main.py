#main.py
"""
基于多Agent的个人决策支持系统 - Phase 1.2
后端入口：FastAPI应用
新增：元认知调度器（快慢回路分离）+ DeepSeek大模型接入
"""
from __future__ import annotations

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
import json
import re
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import (
    DecisionRequest, DecisionReport, FastDecisionReport,
    ConversationCreate, ConversationUpdate, ConversationResponse,
    MessageCreate, MessageResponse,
    FeedbackRequest, ArchiveReport,   # Phase 3.3 新增
    PersonaCreate, PersonaUpdate, PersonaResponse,   # Phase 4.2 新增
    QuantResult,
    ConversationPersonasUpdate  # Phase 4.2.3 新增
)
from agent_core.quant_agent import analyze
from agent_core.risk_agent import assess
from agent_core.mux import merge
from agent_core.ai_client import chat
from storage import (
    init_db, create_conversation, get_conversations, get_conversation,
    update_conversation, delete_conversation, clear_all_conversations,
    add_message, get_messages,
    add_decision_record, get_decision_record, update_feedback, _get_connection,  # Phase 3.3 新增
    get_personas, get_persona, create_persona, update_persona, delete_persona, reset_preset_persona,
    get_conversation_personas,save_conversation_personas
)
from vector_store import (
    store_decision_vector, search_similar_decisions,
    init_user_profile, get_user_profile, add_profile_factor
)
from agent_core.archive_agent import run_archive


app = FastAPI(
    title="个人决策支持系统",
    description="基于多Agent的个人决策支持系统 - Phase 1.2（DeepSeek版）",
    version="0.2.0"
)

app.add_middleware(
    CORSMiddleware,
    # 系统无鉴权、不依赖 cookie：allow_origins=["*"] + allow_credentials=False 是合法组合，
    # 允许局域网内任意设备/任意 IP 的前端连接（后端 IP 漂移场景）；同源托管模式下无需 CORS。
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# 快回路系统提示词
# ==========================================
FAST_LOOP_PROMPT = """你是一个直觉决策顾问。用户面临一个紧急的、需要快速判断的场景。

请直接给出一个简洁、明确的方向性建议。不要进行复杂的量化分析，不要计算概率和赔率。
你的建议应该基于常识、经验法则和直觉判断。

输出格式：
{
  "recommendation": "简洁的行动建议（1-3句话）",
  "reasoning": "简要的判断依据（1-2句话）"
}
"""


# ==========================================
# 元认知调度器：判断走快回路还是慢回路
# ==========================================
def is_fast_loop(scenario: str) -> bool:
    """
    简化版元认知调度器。
    判断条件：
    1. 场景包含紧急时间约束
    2. 场景较短且不涉及量化权衡
    3. 属于日常琐事决策
    """
    scenario_lower = scenario.lower()

    # 紧急时间词
    urgent_words = ["现在", "立刻", "马上", "紧急", "几分钟", "快", "赶紧", "当场"]

    # 日常琐事
    trivial_patterns = ["吃什么", "穿什么", "去哪里玩", "看什么电影", "要不要去"]

    # 涉及量化权衡的复杂决策词（这些应该走慢回路）
    complex_words = [
        "要不要花", "投入多少", "怎么分配", "值不值得",
        "风险", "考试", "复习", "备考", "考研", "职业", "工作",
        "精力", "时间分配", "下注", "重注"
    ]

    # 检查紧急信号
    has_urgent = any(word in scenario_lower for word in urgent_words)

    # 检查是否为复杂决策
    has_complex = any(word in scenario_lower for word in complex_words)

    # 场景长度
    is_short = len(scenario) < 30

    # 决策规则：
    # 紧急 + 短 + 不复杂 → 快回路
    # 复杂决策 → 慢回路
    if has_complex:
        return False
    if has_urgent and is_short:
        return True
    if is_short and any(pattern in scenario_lower for pattern in trivial_patterns):
        return True

    # 默认走慢回路
    return False


# ==========================================
# 路由
# ==========================================

@app.get("/api/health")
async def root():
    return {
        "status": "running",
        "system": "个人决策支持系统",
        "version": "0.2.0",
        "phase": "Phase 1.2 - DeepSeek版",
        "features": ["元认知调度器（快慢回路分离）", "量化分析Agent（AI版）", "风险监控Agent（AI版）"]
    }


@app.post("/api/decision")
async def make_decision(request: DecisionRequest):
    """
    决策分析接口（Phase 1.2 升级版）

    元认知调度器判断回路类型：
    - 快回路：直接调用大模型输出直觉建议
    - 慢回路：量化分析 → 风险监控 → Mux融合
    """

    # ==========================================
    # 元认知调度
    # ==========================================
    if is_fast_loop(request.scenario):
        # -------- 快回路 --------
        response_text = chat(
            system_prompt=FAST_LOOP_PROMPT,
            user_message=request.scenario,
            temperature=0.5,
            max_tokens=512
        )

        # 解析AI输出
        try:
            clean_text = response_text.strip()
            if clean_text.startswith("```"):
                clean_text = re.sub(r'^```(?:json)?\s*', '', clean_text)
                clean_text = re.sub(r'\s*```$', '', clean_text)
            data = json.loads(clean_text)
            recommendation = data.get("recommendation", response_text)
        except (json.JSONDecodeError, KeyError):
            recommendation = response_text

        return FastDecisionReport(
            loop_type="fast",
            recommendation=recommendation,
            note="此建议基于直觉和经验法则，未经过完整的量化分析。如需深度分析，请提供更多细节。"
        )

    else:
        # -------- 慢回路：量化 → 风险 → 场景策略 → Mux（串行） --------
        quant_result = analyze(request.scenario)
        risk_result = assess(request.scenario, quant_result)
        
        # Phase 2 新增：场景策略分析
        from agent_core.scene_agent import analyze_scene
        scene_result = analyze_scene(request.scenario)
        
        decision_report = merge(quant_result, risk_result, scene_result)
        decision_report.loop_type = "slow"
        return decision_report

# ==========================================
# Phase 3.2 新增：对话管理 API
# ==========================================
import json

# 应用启动时初始化数据库
@app.on_event("startup")
async def startup():
    init_db()
        # 初始化用户能力档案（首次运行时创建）
    from datetime import datetime
    now = datetime.now().isoformat()
    initial_profile = {
        "user_id": "default",
        "考试备战能力": 0.85,
        "考试备战能力_updated_at": now,
        "考试备战能力_basis": "软考战损修复验证",
        "行政博弈能力": 0.80,
        "行政博弈能力_updated_at": now,
        "行政博弈能力_basis": "缓考审批博弈验证",
        "技术速通能力": 0.88,
        "技术速通能力_updated_at": now,
        "技术速通能力_basis": "多科目速通验证",
        "风险偏好": "偏激进",
        "风险偏好_updated_at": now,
        "风险偏好_basis": "多次选择高赔率重注"
    }
    init_user_profile(initial_profile)
    print("数据库初始化完成")
    print("=== 版本标识: 2026-05-30-01 ===", flush=True)  # 新增这一行


# -------- 对话 CRUD --------

@app.post("/api/conversations", response_model=ConversationResponse)
async def api_create_conversation(body: ConversationCreate = ConversationCreate()):
    """创建新对话"""
    result = create_conversation(title=body.title)
    return result


@app.get("/api/conversations", response_model=List[ConversationResponse])
async def api_get_conversations():
    """获取所有对话列表"""
    return get_conversations()


@app.get("/api/conversations/{conv_id}", response_model=ConversationResponse)
async def api_get_conversation(conv_id: int):
    """获取单个对话信息"""
    result = get_conversation(conv_id)
    if not result:
        raise HTTPException(status_code=404, detail="对话不存在")
    return result


# 重命名对话
@app.post("/api/conversations/{conv_id}/rename")
async def api_rename_conversation(conv_id: int, body: ConversationUpdate):
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    update_conversation(conv_id, title=body.title)
    return {"status": "ok", "message": "重命名成功"}


@app.post("/api/conversations/{conv_id}/pin")
async def api_toggle_pin(conv_id: int):
    """切换对话置顶状态"""
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    new_pin_state = not conv["is_pinned"]
    update_conversation(conv_id, is_pinned=new_pin_state)
    return {"status": "ok", "is_pinned": new_pin_state}


@app.delete("/api/conversations/{conv_id}")
async def api_delete_conversation(conv_id: int):
    """删除单个对话"""
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    delete_conversation(conv_id)
    return {"status": "ok", "message": "对话已删除"}


@app.delete("/api/conversations")
async def api_clear_all_conversations():
    """清空所有对话"""
    clear_all_conversations()
    return {"status": "ok", "message": "所有对话已清空"}


# -------- 消息操作 --------
"""
在指定对话中发送一条决策消息。
内部会调用完整的 Agent 分析流程（量化→风险→场景策略→Mux），
将用户输入和系统输出都存入数据库。
向量存储和检索在后台异步执行，不影响主流程。

Web 版重构：核心流程抽取为 _agent_pipeline 异步生成器，
同步端点与 SSE 流式端点共用同一管线，消除重复代码。
决策记录在 assistant 消息落库后直接绑定真实 msg_id，
消除原先"msg_id=0 占位 + 事后回填"的并发竞态。
所有同步阻塞调用（LLM/向量库/SQLite）均经 asyncio.to_thread 包装，
避免卡死事件循环（SSE 阶段事件依赖事件循环存活）。
"""

def _sse_format(event: str, data) -> str:
    """格式化为 SSE 帧"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _agent_pipeline(conv_id: int, body: MessageCreate):
    """
    完整决策分析管线（异步生成器）。
    依次 yield (event, data)：("stage", {...}) 阶段事件，最后 ("result", 报告dict) 或 ("error", {...})。
    同步端点只消费最后一个 result/error 事件；SSE 端点把所有事件推送给前端。
    """
    import asyncio

    yield "stage", {"stage": "start"}

    conv = get_conversation(conv_id)
    if not conv:
        yield "error", {"status": 404, "detail": "对话不存在"}
        return

    # 1. 存储用户消息
    await asyncio.to_thread(add_message, conv_id, "user", body.scenario)

    # 2. 运行 Agent 分析流程
    if is_fast_loop(body.scenario):
        # -------- 快回路 --------
        yield "stage", {"stage": "fast"}
        response_text = await asyncio.to_thread(
            chat,
            system_prompt=FAST_LOOP_PROMPT,
            user_message=body.scenario,
            temperature=0.5,
            max_tokens=512
        )
        try:
            clean_text = response_text.strip()
            if clean_text.startswith("```"):
                clean_text = re.sub(r'^```(?:json)?\s*', '', clean_text)
                clean_text = re.sub(r'\s*```$', '', clean_text)
            data = json.loads(clean_text)
            recommendation = data.get("recommendation", response_text)
        except (json.JSONDecodeError, KeyError):
            recommendation = response_text

        report = FastDecisionReport(
            loop_type="fast",
            recommendation=recommendation,
            note="此建议基于直觉和经验法则，未经过完整的量化分析。如需深度分析，请提供更多细节。"
        )
        record_params = None
    else:
        # -------- 慢回路：多分身并行调用 + 能力因子注入 --------
        # 1. 获取所有被选择的分身
        if body.activated_personas:
            # 使用前端传来的分身列表
            persona_ids = [ap["persona_id"] for ap in body.activated_personas]
            all_personas = [p for p in await asyncio.to_thread(get_personas) if p["id"] in persona_ids]
        else:
            # 降级：使用所有分身
            all_personas = await asyncio.to_thread(get_personas)

        record_params = None

        if not all_personas:
            # 如果没有分身（异常情况），降级为单分身中性分析
            yield "stage", {"stage": "quant"}
            quant_result = await asyncio.to_thread(analyze, body.scenario)
            yield "stage", {"stage": "risk"}
            risk_result = await asyncio.to_thread(assess, body.scenario, quant_result)
            yield "stage", {"stage": "scene"}
            from agent_core.scene_agent import analyze_scene
            scene_result = await asyncio.to_thread(analyze_scene, body.scenario)
            yield "stage", {"stage": "merge"}
            report = await asyncio.to_thread(merge, quant_result, risk_result, scene_result)
            report.loop_type = "slow"
            record_params = {
                "p": quant_result.p, "q": quant_result.q, "b": quant_result.b,
                "f_star": quant_result.f_star, "scenario_type": quant_result.scenario_type
            }
        else:
            # 2. 检索历史相似决策（仅一次）
            yield "stage", {"stage": "personas", "names": [p["name"] for p in all_personas]}
            similar = await asyncio.to_thread(search_similar_decisions, body.scenario, 3, 0.5)
            history_context = ""
            if similar:
                history_context = "【历史参考】以下是与当前场景相似的过往决策记录，供参数估算参考：\n"
                for s in similar:
                    meta = s.get("metadata", {})
                    history_context += f"- 决策ID{s['decision_id']}：p={meta.get('p','?')}, b={meta.get('b','?')}, f*={meta.get('f_star','?')}, 场景类型={meta.get('scenario_type','?')}\n"
                history_context += "\n请参考以上历史数据，结合当前场景进行估算。\n"

            # 3. 读取用户能力因子
            user_profile_text = ""
            try:
                profile = await asyncio.to_thread(get_user_profile)
                if profile:
                    user_profile_text = "## 用户画像（基于历史复盘数据，所有分身共享）\n"
                    for key, value in profile.items():
                        if key in ["user_id"] or key.endswith("_updated_at") or key.endswith("_basis"):
                            continue
                        user_profile_text += f"- {key}：{value}\n"
                    user_profile_text += "\n请在估算参数时参考以上画像。不同风险偏好的分身可对同一画像给出不同解读。\n"
            except Exception as e:
                logging.error(f"读取能力因子失败：{e}")

            # 4. 构建增强场景文本
            enhanced_scenario = history_context + "\n当前场景：" + body.scenario

            # 5. 并行调用多个分身的 analyze（to_thread 线程池真并行）
            async def analyze_with_persona(persona):
                # 合并分身的系统 Prompt + 用户画像
                full_prompt = persona["system_prompt"] + "\n\n" + user_profile_text if user_profile_text else persona["system_prompt"]
                return await asyncio.to_thread(analyze, enhanced_scenario, full_prompt)

            tasks = [analyze_with_persona(p) for p in all_personas]
            quant_results = await asyncio.gather(*tasks)

            # 6. 整理各分身结果
            persona_results = []
            for persona, qr in zip(all_personas, quant_results):
                persona_results.append({
                    "persona_id": persona["id"],
                    "name": persona["name"],
                    "risk_preference": persona["risk_preference"],
                    "weight": persona["weight"],
                    "p": qr.p,
                    "q": qr.q,
                    "b": qr.b,
                    "f_star": qr.f_star,
                    "reasoning": qr.reasoning
                })

            # 7. 风险 Agent 和场景 Agent（使用中性分身的结果，若找不到则用第一个）
            yield "stage", {"stage": "risk"}
            neutral_result = next((r for r in persona_results if r.get("risk_preference") == "neutral"), persona_results[0])
            neutral_quant = QuantResult(
                p=neutral_result["p"], q=neutral_result["q"], b=neutral_result["b"],
                f_star=neutral_result["f_star"], scenario_type="", reasoning=""
            )
            risk_result = await asyncio.to_thread(assess, body.scenario, neutral_quant)
            yield "stage", {"stage": "scene"}
            from agent_core.scene_agent import analyze_scene
            scene_result = await asyncio.to_thread(analyze_scene, body.scenario)

            # 8. 加权融合（统一归一化一次）
            if body.activated_personas:
                # 使用前端传来的归一化权重
                persona_weights = {ap["persona_id"]: ap["normalized_weight"] for ap in body.activated_personas}
                for r in persona_results:
                    r["weight"] = persona_weights.get(r["persona_id"], r["weight"])
            total_weight = sum(r["weight"] for r in persona_results) or 1.0
            for r in persona_results:
                r["weight"] = r["weight"] / total_weight
            weighted_f_star = sum(r["f_star"] * r["weight"] for r in persona_results)
            weighted_p = sum(r["p"] * r["weight"] for r in persona_results)
            weighted_q = sum(r["q"] * r["weight"] for r in persona_results)
            weighted_b = sum(r["b"] * r["weight"] for r in persona_results)

            # 9. 生成多分身会商报告
            yield "stage", {"stage": "merge"}
            from agent_core.persona_mux import merge_personas
            report = await asyncio.to_thread(
                merge_personas,
                persona_results=persona_results,
                weighted_f_star=weighted_f_star,
                risk_level=risk_result.risk_level,
                scenario_type=neutral_result.get("scenario_type", ""),
                scene_result=scene_result
            )
            report.loop_type = "slow"
            record_params = {
                "p": weighted_p, "q": weighted_q, "b": weighted_b,
                "f_star": weighted_f_star, "scenario_type": report.scenario_type
            }

    # 3. 存储系统消息（完整报告 JSON），直接拿到真实 msg_id
    system_content = report.model_dump_json() if hasattr(report, 'model_dump_json') else json.dumps(report, default=str)
    assistant_msg = await asyncio.to_thread(add_message, conv_id, "assistant", system_content)

    # 4. 决策归档（直接绑定真实消息ID，无占位符、无回填竞态）
    if record_params is not None:
        decision_id = await asyncio.to_thread(
            add_decision_record,
            conv_id=conv_id, msg_id=assistant_msg["id"], scenario=body.scenario,
            p=record_params["p"], q=record_params["q"], b=record_params["b"],
            f_star=record_params["f_star"],
            scenario_type=record_params["scenario_type"], loop_type="slow"
        )

        # 5. 向量存储（后台线程，不阻塞主流程）
        if decision_id > 0:
            import threading
            def vector_tasks():
                try:
                    similar = search_similar_decisions(body.scenario, top_k=5, threshold=0.7)
                    if similar:
                        logging.info(f"[向量检索] 找到 {len(similar)} 条相似记录")
                except Exception as e:
                    logging.error(f"[向量检索失败] {e}")

                try:
                    store_decision_vector(
                        decision_id=decision_id,
                        scenario=body.scenario,
                        metadata={
                            "p": record_params["p"],
                            "q": record_params["q"],
                            "b": record_params["b"],
                            "f_star": record_params["f_star"],
                            "scenario_type": record_params["scenario_type"],
                            "conv_id": conv_id
                        }
                    )
                    logging.info(f"[向量存储成功] decision_id={decision_id}")
                except Exception as e:
                    logging.error(f"[向量存储失败] decision_id={decision_id}, error={e}")

            threading.Thread(target=vector_tasks, daemon=True).start()

    logging.info(f"[消息成功] conv_id={conv_id}, loop_type={report.loop_type}")
    yield "result", json.loads(system_content)


@app.post("/api/conversations/{conv_id}/messages")
async def api_send_message(conv_id: int, body: MessageCreate):
    """发送消息（同步版：一次性返回完整报告，供降级/兼容使用）"""
    try:
        result = None
        async for event, data in _agent_pipeline(conv_id, body):
            if event == "error":
                raise HTTPException(status_code=data.get("status", 500), detail=data.get("detail", "管线执行失败"))
            result = data
        if result is None:
            raise HTTPException(status_code=500, detail="管线未产生结果")
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/conversations/{conv_id}/messages/stream")
async def api_send_message_stream(conv_id: int, body: MessageCreate):
    """发送消息（SSE 流式版：推送 stage 阶段事件 + result 最终报告）"""
    from fastapi.responses import StreamingResponse

    async def event_gen():
        try:
            async for event, data in _agent_pipeline(conv_id, body):
                yield _sse_format(event, data)
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield _sse_format("error", {"status": 500, "detail": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/conversations/{conv_id}/messages", response_model=List[MessageResponse])
async def api_get_messages(conv_id: int):
    """获取指定对话的所有消息"""
    return get_messages(conv_id)

@app.post("/api/conversations/{conv_id}/messages/{msg_id}/feedback")
async def api_submit_feedback(conv_id: int, msg_id: int, body: FeedbackRequest):
    """提交决策反馈，触发复盘归档"""
    # 决策记录在消息落库时已直接绑定真实 msg_id（无占位符），此处直接查询
    conn = _get_connection()
    row = conn.execute(
        "SELECT id FROM decision_records WHERE message_id = ? AND conversation_id = ?",
        (msg_id, conv_id)
    ).fetchone()
    conn.close()

    decision_id: int | None = row["id"] if row else None
    record = get_decision_record(decision_id) if decision_id is not None else None

    # 如果还没有找到记录，尝试从 messages 表重建决策记录
    if record is None:
        conn_msg = _get_connection()
        msg_row = conn_msg.execute(
            "SELECT content FROM messages WHERE id = ?", (msg_id,)
        ).fetchone()
        conn_msg.close()

        if msg_row is None:
            raise HTTPException(status_code=404, detail="消息不存在")

        scenario = msg_row["content"]
        if is_fast_loop(scenario):
            raise HTTPException(status_code=400, detail="快回路消息不支持反馈")

        quant_result = analyze(scenario)
        risk_result = assess(scenario, quant_result)
        from agent_core.scene_agent import analyze_scene
        scene_result = analyze_scene(scenario)

        decision_id = add_decision_record(
            conv_id=conv_id, msg_id=msg_id, scenario=scenario,
            p=quant_result.p, q=quant_result.q, b=quant_result.b,
            f_star=quant_result.f_star,
            scenario_type=quant_result.scenario_type, loop_type="slow"
        )
        record = get_decision_record(decision_id)

    # 最终检查：必须拿到有效的决策记录
    if record is None or decision_id is None:
        raise HTTPException(status_code=404, detail="决策记录不存在")

    # 更新反馈信息
    update_feedback(decision_id, body.feedback_type, body.feedback_text)

    # 运行复盘归档Agent
    archive_report = run_archive(
        decision_id=decision_id,
        initial_f_star=record["f_star"],
        p=record["p"],
        q=record["q"],
        b=record["b"],
        scenario_type=record["scenario_type"],
        feedback_type=body.feedback_type,
        feedback_text=body.feedback_text or ""
    )

    return {
        "status": "ok",
        "archive_report": archive_report.dict()
    }

@app.get("/api/user-profile")
async def api_get_profile():
    """获取当前用户能力档案"""
    return get_user_profile()


@app.post("/api/user-profile/add-factor")
async def api_add_factor(factor_name: str, value: float, basis: str):
    """用户确认后添加新因子"""
    add_profile_factor(factor_name, value, basis)
    return {"status": "ok", "factor_name": factor_name}


# ==========================================
# Phase 4.2 新增：分身管理 API
# ==========================================

# 自定义分身的核心原则 → Prompt 转换
def _generate_persona_prompt(risk_preference: str, core_principle: str) -> str:
    """根据风险偏好和核心原则生成系统 Prompt"""
    base_prompts = {
        "aggressive": "你倾向于在胜率和赔率明确占优时建议加大投入。在估算参数时，你可以基于对机会的乐观判断，给出相对积极的 p 和 b 估算。你相信机会稍纵即逝，优质窗口值得全力出击。",
        "neutral": "你严格按照凯利公式的数学结论给出建议，不做情绪化调整。你追求长期复利最优，而非单次收益最大。在估算参数时保持中立客观。",
        "conservative": "你倾向于在信息不完全或赔率不明时建议观望或做空。在估算参数时，你会谨慎评估潜在风险，对 p 和 b 的估算相对保守。你的首要原则是避免清零，生存优先于收益。",
        "custom": core_principle if core_principle else "你根据用户设定的核心原则进行分析。"
    }
    return base_prompts.get(risk_preference, base_prompts["custom"])


@app.get("/api/personas", response_model=List[PersonaResponse])
async def api_get_personas():
    """获取所有分身列表"""
    return get_personas()


@app.post("/api/personas", response_model=PersonaResponse)
async def api_create_persona(body: PersonaCreate):
    """创建自定义分身"""
    # 检查自定义分身数量是否已达上限
    all_personas = get_personas()
    custom_count = sum(1 for p in all_personas if not p["is_preset"])
    if custom_count >= 3:
        raise HTTPException(status_code=400, detail="最多创建3个自定义分身")
    
    # 重名校验
    existing_names = [p["name"] for p in all_personas]
    if body.name in existing_names:
        raise HTTPException(status_code=400, detail="已存在同名分身")
    
    system_prompt = _generate_persona_prompt(body.risk_preference, body.core_principle or "")
    persona_id = create_persona(
        name=body.name,
        risk_preference=body.risk_preference,
        core_principle=body.core_principle or "",
        system_prompt=system_prompt,
        weight=0.2  # 默认权重
    )
    if persona_id < 0:
        raise HTTPException(status_code=500, detail="创建分身失败")
    result = get_persona(persona_id)
    if not result:
        raise HTTPException(status_code=500, detail="分身创建后无法读取")
    return result


@app.post("/api/personas/{persona_id}/update", response_model=PersonaResponse)
async def api_update_persona(persona_id: int, body: PersonaUpdate):
    """修改分身信息"""
    persona = get_persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="分身不存在")

    # 重名校验（如果修改了名称）
    if body.name and body.name != persona["name"]:
        existing_names = [p["name"] for p in get_personas()]
        if body.name in existing_names:
            raise HTTPException(status_code=400, detail="已经存在同名分身！请换成其他名字")

    # 如果修改了风险偏好，且是自定义分身，重新生成 system_prompt
    system_prompt = None
    if body.risk_preference and not persona["is_preset"]:
        core_principle = body.core_principle if body.core_principle else persona["core_principle"]
        system_prompt = _generate_persona_prompt(body.risk_preference, core_principle)

    update_persona(
        persona_id=persona_id,
        name=body.name if not persona["is_preset"] else None,  # 预置分身不可改名
        core_principle=body.core_principle if not persona["is_preset"] else None,  # 预置分身不可改原则
        system_prompt=system_prompt,
        weight=body.weight
    )

    # 如果修改了 risk_preference，同步更新 risk_preference 字段
    if body.risk_preference and not persona["is_preset"]:
        conn = _get_connection()
        conn.execute("UPDATE personas SET risk_preference = ? WHERE id = ?", (body.risk_preference, persona_id))
        conn.commit()
        conn.close()
    
    return get_persona(persona_id)


@app.delete("/api/personas/{persona_id}")
async def api_delete_persona(persona_id: int):
    """删除自定义分身"""
    persona = get_persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="分身不存在")
    if persona["is_preset"]:
        raise HTTPException(status_code=400, detail="预置分身不可删除")
    delete_persona(persona_id)
    return {"status": "ok", "message": "分身已删除"}


@app.post("/api/personas/{persona_id}/reset")
async def api_reset_persona(persona_id: int):
    """重置预置分身为默认值"""
    result = reset_preset_persona(persona_id)
    if not result:
        raise HTTPException(status_code=400, detail="重置失败，请确认该分身为预置分身")
    return result


# ==========================================
# Phase 4.2.3 新增：对话分身关联 API
# ==========================================

@app.get("/api/conversations/{conv_id}/personas")
async def api_get_conversation_personas(conv_id: int):
    """获取指定对话激活的分身ID列表"""
    return get_conversation_personas(conv_id)


@app.post("/api/conversations/{conv_id}/personas")
async def api_save_conversation_personas(conv_id: int, body: ConversationPersonasUpdate):
    """保存指定对话激活的分身列表"""
    save_conversation_personas(conv_id, body.persona_ids)
    return {"status": "ok", "persona_ids": body.persona_ids}


# ==========================================
# Web 前端静态托管（可选）
# 将 web-frontend 构建产物复制到本目录的 static/ 下即可生效：
# 任何局域网设备访问 http://<后端IP>:8000 直接使用，同源零 CORS。
# 注意：必须挂在所有 API 路由之后，已有路由优先匹配。
# ==========================================
import os as _os
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


# 未匹配的 /api/* 统一返回 JSON 404（需定义在静态挂载之前）
@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def api_not_found(rest: str):
    raise HTTPException(status_code=404, detail=f"接口不存在: /api/{rest}")


class SpaStaticFiles(StaticFiles):
    """SPA 静态托管：找不到文件时回退 index.html，支持前端 history 路由深链（/personas 等）。"""
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404:
                return await super().get_response("index.html", scope)
            raise

_STATIC_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "static")
if _os.path.isdir(_STATIC_DIR):
    app.mount("/", SpaStaticFiles(directory=_STATIC_DIR, html=True), name="web-frontend")
    logging.info(f"[静态托管] Web 前端已挂载: {_STATIC_DIR}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)