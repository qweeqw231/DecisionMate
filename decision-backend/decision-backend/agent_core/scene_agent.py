#agent_core/scene_agent.py
"""
场景策略Agent
职责：识别用户输入中的特定场景，加载对应策略模板，输出分阶段建议。

Phase 2 实现：
- 考试复合体场景模板（含5项策略库）
- 模板接口标准化，为后续场景扩展提供统一规范

Phase 3.1 修复：
- 年份动态化（仅跨年时修正次年，不再自动推进已过日期）
- 模糊日期映射（上旬→5日，中旬→15日，下旬→25日）
- 仅提供月份的考试映射为当月1日，并提示用户提供更细粒度日期
- reference 文案优化（改为“历史参考”格式，不再使用第三人称）
- 学期级复合体标签修正（≥3场且跨度≥2个月，2场>7天为长间隔复合体）
- 考间缓释 reference 时间线修正（软考→飞控实战中为睡眠恢复）
"""

import re
from datetime import datetime, timedelta
from typing import List
from models.schemas import SceneResult, StrategyItem

# ==========================================
# 场景模板注册表（未来扩展只需在此添加）
# ==========================================
SCENE_TEMPLATES = {
    "exam_complex": {
        "name": "考试复合体",
        "trigger_keywords": ["考试", "备考", "复习", "笔试", "面试", "科目"],
        "trigger_multi_exam": True,
        "description": "两个及以上考试在时间上紧密相邻，导致状态耦合"
    }
}


def analyze_scene(scenario: str) -> SceneResult:
    """
    分析用户输入，识别场景类型并加载对应策略模板。
    """
    exam_dates = _extract_exam_dates(scenario)

    if exam_dates and len(exam_dates) >= 2:
        return _handle_exam_complex(scenario, exam_dates)

    return SceneResult(
        scene_recognized=False,
        scene_type="通用场景",
        complex_type="无",
        strategies=[],
        timeline_summary="未检测到多考试日程，使用标准决策分析。",
        reasoning="用户输入中未检测到两个及以上考试日期，不触发考试复合体策略。"
    )


def _extract_exam_dates(text: str) -> List[dict]:
    """
    从文本中提取考试日期和名称。
    支持格式：
    - 精确日期：5月23日软考、5.23软考、5-23软考
    - 模糊日期：3月上旬教资笔试、5月下旬飞控
    - 仅有月份：3月教资笔试、6月软考（映射为当月1日）
    """
    exams = []

    # ==========================================
    # 匹配模式一：精确日期（月+日+考试名）
    # ==========================================
    patterns = [
        r'(\d{1,2})月(\d{1,2})[日号]?\s*([^\s，,。.]{1,20}?(?:考试|面试|笔试|科目|认证|机考))',
        r'(\d{1,2})\.(\d{1,2})\s*([^\s，,。.]{1,20}?(?:考试|面试|笔试|科目|认证|机考))',
        r'(\d{1,2})-(\d{1,2})\s*([^\s，,。.]{1,20}?(?:考试|面试|笔试|科目|认证|机考))',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            month = int(match[0])
            day = int(match[1])
            name = match[2].strip()
            if 1 <= month <= 12 and 1 <= day <= 31:
                exams.append({
                    "month": month,
                    "day": day,
                    "name": name,
                    "date_str": f"{month}月{day}日",
                    "is_approximate": False,
                    "approx_note": ""
                })

    # ==========================================
    # 匹配模式二：模糊日期（X月上旬/Y月中旬/Z月下旬 + 考试名）
    # ==========================================
    fuzzy_pattern = r'(\d{1,2})月(上旬|中旬|下旬)\s*([^\s，,。.]{2,20})'
    fuzzy_matches = re.findall(fuzzy_pattern, text)

    fuzzy_day_map = {"上旬": 5, "中旬": 15, "下旬": 25}

    for match in fuzzy_matches:
        month = int(match[0])
        period = match[1]
        name = match[2].strip()
        day = fuzzy_day_map[period]

        if 1 <= month <= 12:
            approx_note = f"（{month}月{period}映射为{month}月{day}日，请手动确认具体日期）"
            exams.append({
                "month": month,
                "day": day,
                "name": name,
                "date_str": f"{month}月{day}日",
                "is_approximate": True,
                "approx_note": approx_note
            })

    # ==========================================
    # 匹配模式三：仅有月份（X月 + 考试名，无具体日期）
    # ==========================================
    # 扩充考试名称关键词，覆盖“软考”、“国考”等以“考”结尾但不带“考试”的简称
    month_only_pattern = r'(\d{1,2})月(?!\d{1,2}[日号])\s*([^\s，,。.]{2,20}(?:考试|面试|笔试|科目|认证|机考|考|试|测评|考核))'
    month_only_matches = re.findall(month_only_pattern, text)

    existing_names = {exam["name"] for exam in exams}

    for match in month_only_matches:
        month = int(match[0])
        name = match[1].strip()
        day = 1

        if name in existing_names:
            continue

        if 1 <= month <= 12:
            approx_note = f"（仅提供{month}月，自动映射为{month}月1日，建议提供具体日期以获得更精确的间隔分析）"
            exams.append({
                "month": month,
                "day": day,
                "name": name,
                "date_str": f"{month}月{day}日",
                "is_approximate": True,
                "approx_note": approx_note
            })

    # 兜底：如果仍然不足2个，用极度宽松的正则提取“X月”后面紧跟的任何名称
    if len(exams) < 2:
        fallback_pattern = r'(\d{1,2})月(?!\d{1,2}[日号])\s*([^\s，,。.\d]{2,10})'
        fallback_matches = re.findall(fallback_pattern, text)
        existing_names = {exam["name"] for exam in exams}

        for match in fallback_matches:
            month = int(match[0])
            name = match[1].strip()
            day = 1

            if name in existing_names:
                continue

            if 1 <= month <= 12:
                approx_note = f"（仅提供{month}月，自动映射为{month}月1日，建议提供具体日期以获得更精确的间隔分析）"
                exams.append({
                    "month": month,
                    "day": day,
                    "name": name,
                    "date_str": f"{month}月{day}日",
                    "is_approximate": True,
                    "approx_note": approx_note
                })

    # ==========================================
    # 匹配模式四：宽松匹配（仅月+日+简短名称，无考试等后缀关键词）
    # ==========================================
    if len(exams) < 2:
        loose_pattern = r'(\d{1,2})月(\d{1,2})[日号]?\s*([\u4e00-\u9fa5a-zA-Z]{2,10})'
        loose_matches = re.findall(loose_pattern, text)
        for match in loose_matches:
            month = int(match[0])
            day = int(match[1])
            name = match[2].strip()
            if 1 <= month <= 12 and 1 <= day <= 31:
                exams.append({
                    "month": month,
                    "day": day,
                    "name": name,
                    "date_str": f"{month}月{day}日",
                    "is_approximate": False,
                    "approx_note": ""
                })

    # ==========================================
    # 年份推断
    # ==========================================
    exams = _infer_years(exams, text)

    # ==========================================
    # 去重与排序
    # 同一月日同名考试，保留年份最大的（跨年后应为次年）
    # ==========================================
    merged = {}
    for exam in exams:
        key = (exam["month"], exam["day"], exam["name"])
        if key not in merged or exam["year"] > merged[key]["year"]:
            merged[key] = exam
    unique_exams = list(merged.values())
    unique_exams.sort(key=lambda x: (x["year"], x["month"], x["day"]))
    return unique_exams


def _infer_years(exams: List[dict], text: str) -> List[dict]:
    """
    推断考试年份。

    规则：
    1. 若文本中明确写有年份（如"2025年"），所有考试使用该年份。
    2. 否则全部默认当前年份。
    3. 多场考试之间：若相邻考试月份差值绝对值 > 6，则判定为跨年。
       月份较小的考试取次年，月份较大的取当前年份。
    4. 不再自动推进已过日期（用户谈论的多是今年的考试）。
    """
    current_year = datetime.now().year

    # 检测用户是否指定了年份
    year_match = re.search(r'(\d{4})年', text)
    if year_match:
        specified_year = int(year_match.group(1))
        for exam in exams:
            exam["year"] = specified_year
        return exams

    # 未指定年份，全部默认当前年份
    for exam in exams:
        exam["year"] = current_year

    # 多场考试：跨年判定
    if len(exams) >= 2:
        # 遍历相邻考试，若月份骤降且差值 > 6，则跨年
        for i in range(len(exams) - 1):
            if exams[i+1]["month"] < exams[i]["month"] and abs(exams[i+1]["month"] - exams[i]["month"]) > 6:
                exams[i+1]["year"] = exams[i]["year"] + 1
            else:
                exams[i+1]["year"] = exams[i]["year"]

    return exams


def _handle_exam_complex(scenario: str, exam_dates: List[dict]) -> SceneResult:
    """处理考试复合体场景"""

    # 计算间隔天数
    intervals = []
    for i in range(len(exam_dates) - 1):
        d1 = datetime(exam_dates[i]["year"], exam_dates[i]["month"], exam_dates[i]["day"])
        d2 = datetime(exam_dates[i+1]["year"], exam_dates[i+1]["month"], exam_dates[i+1]["day"])
        gap = (d2 - d1).days
        intervals.append(gap)

    # 计算总跨度（第一场到最后一场）
    d_first = datetime(exam_dates[0]["year"], exam_dates[0]["month"], exam_dates[0]["day"])
    d_last = datetime(exam_dates[-1]["year"], exam_dates[-1]["month"], exam_dates[-1]["day"])
    total_span_days = (d_last - d_first).days

    # ==========================================
    # 复合体类型判定（修正版）
    # ==========================================
    min_gap = min(intervals) if intervals else 999
    exam_count = len(exam_dates)

    if exam_count == 2:
        # 2场考试：按最短间隔分类
        if min_gap <= 3:
            complex_type = "天级复合体"
            complex_desc = f"最短间隔仅{min_gap}天，状态无法完全重置"
        elif min_gap <= 7:
            complex_type = "周级复合体"
            complex_desc = f"最短间隔{min_gap}天，耦合强度减弱但仍有技能迁移效应"
        else:
            complex_type = "长间隔复合体"
            complex_desc = f"间隔{min_gap}天，耦合强度较弱，可按独立考试分别准备"
    else:
        # ≥3场考试：先看最短间隔，再看总跨度
        if min_gap <= 3:
            complex_type = "天级复合体"
            complex_desc = f"多场考试中最近间隔仅{min_gap}天，存在天级叠加"
        elif min_gap <= 7:
            complex_type = "周级复合体"
            complex_desc = f"多场考试中最近间隔{min_gap}天，存在周级耦合"
        else:
            # 最短间隔 > 7天，看总跨度
            if total_span_days >= 60:
                complex_type = "学期级复合体"
                complex_desc = f"整个考试季跨度约{total_span_days}天（约{total_span_days//30}个月），多场考试形成压力波形"
            else:
                complex_type = "长间隔复合体"
                complex_desc = f"多场考试总跨度{total_span_days}天（<2个月），耦合强度较弱"

    # 生成策略
    strategies = _generate_exam_strategies(exam_dates, intervals)

    # 生成时间线摘要
    timeline_parts = []
    for i, exam in enumerate(exam_dates):
        approx_mark = "（近似）" if exam.get("is_approximate") else ""
        timeline_parts.append(f"{exam['year']}年{exam['date_str']} {exam['name']}{approx_mark}")
        if i < len(exam_dates) - 1:
            timeline_parts.append(f"  ↓ (间隔{intervals[i]}天)")
    timeline_summary = "\n".join(timeline_parts)

    # 模糊日期提醒
    approx_warning = ""
    for exam in exam_dates:
        if exam.get("is_approximate") and exam.get("approx_note"):
            approx_warning += f"\n⚠️ {exam['approx_note']}"

    reasoning = (
        f"检测到{exam_count}场考试紧密相邻，"
        f"{complex_desc}。"
        f"自动加载考试复合体策略模板（考前保留、考间缓释、技能迁移、终局评判、缓释梯度）。"
        f"{approx_warning}"
    )

    return SceneResult(
        scene_recognized=True,
        scene_type="考试复合体",
        complex_type=complex_type,
        strategies=strategies,
        timeline_summary=timeline_summary,
        reasoning=reasoning
    )


def _generate_exam_strategies(exam_dates: List[dict], intervals: List[int]) -> List[StrategyItem]:
    """根据考试日期生成分阶段策略"""

    strategies = []

    # ==========================================
    # 策略1：考前保留策略（第一场考试前）
    # ==========================================
    first_exam = exam_dates[0]
    first_date = f"{first_exam['month']}月{first_exam['day']}日"
    strategies.append(StrategyItem(
        phase="考前保留期",
        date_range=f"现在 – {first_date}",
        strategy_name="考前保留策略",
        suggestion=(
            f"在{first_exam['name']}前，建议复习投入上限80%-90%，"
            f"为后续{len(exam_dates)-1}场考试预留10%-20%心理带宽。"
            f"潜意识为后续考试预留认知资源是自动的风险规避策略，不要强行推到100%。"
        ),
        reference="历史参考：在软考→飞控的实战中，复习时潜意识会为后续考试预留认知资源，考前保留策略验证有效。"
    ))

    # ==========================================
    # 策略2：考间缓释策略（每两场之间）
    # ==========================================
    for i in range(len(exam_dates) - 1):
        current = exam_dates[i]
        next_exam = exam_dates[i+1]
        gap = intervals[i]

        if gap <= 2:
            release_suggestion = (
                f"{current['name']}结束后，安排{gap}天左右的低认知负荷活动"
                f"（散步、轻度活动、充足睡眠）。"
                f"不强行学习（避免厌学），也不彻底放纵（避免生物钟紊乱）。"
            )
        elif gap <= 7:
            release_suggestion = (
                f"{current['name']}结束后，当天晚上彻底放松。"
                f"第二天开始进入{next_exam['name']}的正常备考节奏，"
                f"考前1天降低强度，调整为轻度复习和休息。"
                f"间隔{gap}天足够完整复习，不必全程高压。"
            )
        else:
            release_suggestion = (
                f"{current['name']}结束后稍作休息（半天到1天），"
                f"然后按正常节奏备考{next_exam['name']}。"
                f"间隔{gap}天足够充分准备，注意考前1-2天适当降低强度。"
            )

        strategies.append(StrategyItem(
            phase=f"第{i+1}场考后缓释期",
            date_range=f"{current['date_str']}考后 – {next_exam['date_str']}考前",
            strategy_name="考间缓释策略",
            suggestion=release_suggestion,
            reference="历史参考：在软考→飞控的实战中，考间晚上睡了12小时，白天保持1.5小时午睡，不强制学习，以彻底恢复精神和体力。考间缓释策略验证有效。"
        ))

    # ==========================================
    # 策略3：技能迁移策略
    # ==========================================
    if len(exam_dates) >= 2:
        strategies.append(StrategyItem(
            phase="技能迁移期",
            date_range=f"{exam_dates[0]['date_str']} – {exam_dates[-1]['date_str']}",
            strategy_name="技能迁移策略",
            suggestion=(
                f"主动识别{exam_dates[0]['name']}中可迁移的技能并用于后续考试。"
                f"常见可迁移技能：时间分配、答题节奏、跳过难题的果断性、编答案能力、心理调节。"
            ),
            reference="历史参考：在软考→飞控的实战中，答题节奏和编答案能力成功迁移，技能迁移策略验证有效。"
        ))

    # ==========================================
    # 策略4：终局评判策略
    # ==========================================
    last_exam = exam_dates[-1]
    strategies.append(StrategyItem(
        phase="终局评判期",
        date_range=f"{last_exam['date_str']}考后",
        strategy_name="终局评判策略",
        suggestion=(
            f"以'是否尽力'为最终评价标准，而非外部分数。"
            f"尽力即是胜仗。任务序列完成本身即是奖赏，减少分数焦虑对下一阶段任务的干扰。"
        ),
        reference="历史参考：在2026年上半年考试季中，'尽力就好'是终局评判的核心标准，有效减少了分数焦虑。"
    ))

    # ==========================================
    # 策略5：缓释梯度设计（≥3场考试时触发）
    # ==========================================
    if len(exam_dates) >= 3:
        strategies.append(StrategyItem(
            phase="学期级缓释设计",
            date_range=f"{exam_dates[0]['date_str']} – {exam_dates[-1]['date_str']}考后",
            strategy_name="缓释梯度设计",
            suggestion=(
                f"在每次大考后设置不同强度的缓释窗口："
                f"考后当晚轻度娱乐 → 第二天全天低负荷活动 → 第三天开始保温学习。"
                f"避免高压锅突然掀盖或持续闷烧。"
            ),
            reference="历史参考：飞控考后当晚正常作息，次日轻度活动，第三日恢复日常节奏。缓释梯度设计验证有效。"
        ))

    return strategies