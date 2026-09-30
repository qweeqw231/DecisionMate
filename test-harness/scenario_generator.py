# scenario_generator.py
"""
批量决策场景生成器。
基于《个人决策支持系统文档》中的决策原则分类，调用 DeepSeek 生成自然语言场景，
解析校验（含本地回路预判）后写入 test_results.db。

用法：
    python scenario_generator.py                     # 生成全部类别（目标 112 条）
    python scenario_generator.py --category fast_trivial --limit 3   # 单类别试跑
    python scenario_generator.py --list              # 查看类别
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ---- 引入后端的 ai_client（复用 DeepSeek 调用），并显式加载后端 .env ----
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "decision-backend", "decision-backend")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.abspath(BACKEND_DIR), ".env"))

from agent_core.ai_client import chat  # noqa: E402
import test_storage  # noqa: E402


# ============================================================
# 与 main.py is_fast_loop 保持一致的本地回路预判（用于生成校验）
# 若 main.py 的分类规则变更，此处需同步
# ============================================================
def local_is_fast_loop(scenario: str) -> bool:
    scenario_lower = scenario.lower()
    urgent_words = ["现在", "立刻", "马上", "紧急", "几分钟", "快", "赶紧", "当场"]
    trivial_patterns = ["吃什么", "穿什么", "去哪里玩", "看什么电影", "要不要去"]
    complex_words = [
        "要不要花", "投入多少", "怎么分配", "值不值得",
        "风险", "考试", "复习", "备考", "考研", "职业", "工作",
        "精力", "时间分配", "下注", "重注"
    ]
    has_urgent = any(w in scenario_lower for w in urgent_words)
    has_complex = any(w in scenario_lower for w in complex_words)
    is_short = len(scenario) < 30
    if has_complex:
        return False
    if has_urgent and is_short:
        return True
    if is_short and any(p in scenario_lower for p in trivial_patterns):
        return True
    return False


# ============================================================
# 场景类别定义（源自架构文档的决策原则）
# ============================================================
USER_BG = (
    "用户是一名大学生，真实背景素材：软考（软件设计师）备考、飞行控制原理考试、"
    "教师资格证考试、因病办理缓考的行政流程博弈、考研 vs 直接就业的抉择、"
    "个人资产配置（生活费/奖学金/小额投资）、多门课程并行期末周。"
    "场景请优先复用这些背景，也可合理外溢到实习选择、项目取舍、时间安排等学生场景。"
)

CATEGORIES = {
    "high_odds_bet": {
        "name": "高赔率重注",
        "expected_loop": "slow",
        "target": 15,
        "doc": "当胜率p与赔率b明确占优（期望值显著为正且窗口稀缺）时，应敢于加大投入（f*较大）。"
               "典型特征：机会窗口短暂、自身优势可验证、下行损失可控、上行收益数倍。",
        "seeds": [
            "距离软考还有45天，我已经完成一轮复习且模考正确率78%，是否应该把每天娱乐时间全部砍掉，把复习强度拉满冲刺高分？",
            "有个含金量很高的竞赛报名后天截止，我目前的项目完成度约70%，要不要押上接下来两周几乎所有的课余时间冲一把？",
        ],
        "variation": "变换机会类型（考试/竞赛/实习申请/投资/项目窗口）、时间尺度（几天到一学期）、资源类型（时间/金钱/精力）。",
    },
    "low_odds_short": {
        "name": "低赔率做空",
        "expected_loop": "slow",
        "target": 12,
        "doc": "当期望值接近零或为负、赔率不划算时，应建议观望、减仓或明确放弃（f*接近0甚至为负）。"
               "典型特征：胜率低、回报平庸、机会成本高、沉没成本诱人继续。",
        "seeds": [
            "一门选修课已经上了半学期，内容水但退课会留下记录，继续上要再花40小时，值得坚持吗？",
            "朋友拉我参与一个需要先交3000元培训费的兼职项目，宣传说月入过万，我该投吗？",
        ],
        "variation": "变换诱惑类型（金钱/面子/沉没成本/同伴压力），确保期望值模糊或偏负。",
    },
    "advantage_calibration": {
        "name": "优势积累动态校准",
        "expected_loop": "slow",
        "target": 15,
        "doc": "决策不是一次性的：随着执行推进、信息更新，应动态校准p/b估计并调整投入。"
               "典型特征：阶段性反馈（模考成绩、项目里程碑）、需要决定加码/维持/退出。",
        "seeds": [
            "飞控考试复习到一半，最近三次章节测验分别是60/75/88分，原计划最后两周加码冲刺，现在该维持原计划还是调整？",
            "准备教资笔试的同时，一个实习机会要求每周到岗3天，我的模考分数刚过线，该怎么重新分配精力？",
        ],
        "variation": "变换反馈信号方向（上升/停滞/下滑）、距截止时间的远近、替代机会的有无。",
    },
    "zoh_waiting": {
        "name": "ZOH离散采样等待",
        "expected_loop": "slow",
        "target": 12,
        "doc": "零阶保持（ZOH）原则：在信息不足或时机未到时，保持当前状态、设定下次采样检查点，"
               "而不是焦虑地连续微调。典型特征：等待审批/等待成绩/等待对方回复期间的最优动作是'做好手头事+定时检查'。",
        "seeds": [
            "缓考申请已经提交教务处，审批要5个工作日，这期间我是该天天去催，还是按原计划复习其他科目并设定检查节点？",
            "投了15份实习简历两周没回音，现在该立刻海投50份，还是分析简历问题后设定一周后的检查点？",
        ],
        "variation": "变换等待对象（行政审批/考试成绩/他人回复/市场信号）、检查点间隔、等待期间的可并行任务。",
    },
    "strategic_rest": {
        "name": "战略性休整",
        "expected_loop": "slow",
        "target": 10,
        "doc": "当系统出现过载信号（连续熬夜、效率骤降、健康报警）时，主动休整不是放弃而是保全局的最优策略。"
               "典型特征：多任务并行崩溃边缘、需要决定砍掉什么、休整后如何恢复。",
        "seeds": [
            "期末周三门考试连排，我已经连续五天只睡4小时，今天效率明显崩了，要不要牺牲明晚的复习时间睡一觉？",
            "备考软考期间接了一个能赚钱的私活，但两周下来两边都在掉进度，是不是该停掉一个？",
        ],
        "variation": "变换过载来源（学业/兼职/社交/健康）、休整成本、恢复后的追赶空间。",
    },
    "exam_complex": {
        "name": "考试复合体",
        "expected_loop": "slow",
        "target": 18,
        "doc": "考试决策是多阶段复合体：天级（临场24-48小时策略）、周级（冲刺节奏与取舍）、"
               "学期级（多考试组合的资源排布与弃保）。系统应识别复合体层级并给出分阶段策略时间线。",
        "seeds": [
            "明天上午考飞控，我现在还有两章没看完，今晚该通宵还是保住睡眠？（天级）",
            "未来10天有软考和一门专业课期末，软考我准备更充分但专业课学分更高，怎么排布复习节奏？（周级）",
            "这学期有教资、六级、三门专业课期末，加上考研启动，我该怎么排整学期的优先级？（学期级）",
        ],
        "variation": "均衡覆盖天级/周级/学期级三个子类（subcategory字段标注），变换考试组合与约束。",
    },
    "fast_trivial": {
        "name": "快回路日常琐事",
        "expected_loop": "fast",
        "target": 20,
        "doc": "紧急或琐碎的日常判断应走直觉快回路：不量化、不计算，直接给方向性建议。"
               "【硬性约束】场景必须少于25个字，且含'吃什么/穿什么/要不要去/马上/现在/赶紧'等词之一，"
               "且绝不能出现'考试/复习/备考/考研/风险/工作/投入/分配/精力'等复杂决策词。",
        "seeds": [
            "中午吃什么？",
            "下雨了，现在要不要赶紧收衣服？",
            "晚上穿什么去聚餐？",
        ],
        "variation": "变换琐事类型（吃/穿/出行/即时小事），全部保持极短、口语化。",
    },
    "ethics_shutdown": {
        "name": "伦理关机",
        "expected_loop": "slow",
        "target": 10,
        "doc": "涉及具体他人的伦理抉择（代考、作弊、撒谎、利益交换）不应被凯利公式量化，"
               "系统应明确拒绝计算并指出这是价值观问题而非概率问题。"
               "【硬性约束】场景必须超过40个字、描述具体情境与利害关系，避免'要不要去'这类快回路触发词。",
        "seeds": [
            "室友飞控考试想让我把笔记里整理的题库答案传给他，他平时帮过我很多忙，但这次是明确违反考场纪律的行为，我很纠结该怎么回应他。",
            "辅导员暗示我，如果缓考材料里把病情写得严重一些更容易批，还举了别人的例子，我不知道要不要照做。",
        ],
        "variation": "变换伦理困境类型（学术诚信/人际忠诚/规则灰色地带/利益交换），确保涉及具体他人且两难。",
    },
}

SYS_PROMPT = (
    "你是一名决策测试场景工程师。你的任务是生成逼真、具体、第一人称的决策场景文本，"
    "用于测试一个个人决策支持系统。你只输出合法的 JSON 数组，不输出任何其他文字。"
)


def build_prompt(key: str, cfg: dict, n: int) -> str:
    seeds = "\n".join(f"  - {s}" for s in cfg["seeds"])
    sub_field = ""
    if key == "exam_complex":
        sub_field = '，"subcategory" 必须是 "天级"/"周级"/"学期级" 之一且三个子类数量尽量均衡'
    return f"""请生成 {n} 条「{cfg['name']}」类别的决策场景。

【类别定义】{cfg['doc']}

【用户背景】{USER_BG}

【种子示例】（仅作风格参考，请生成不同的新场景）
{seeds}

【变体要求】{cfg['variation']}

【输出格式】JSON 数组，每个元素：
[{{"subcategory": "子类名（无子类则填类别名）", "scenario": "第一人称中文场景文本"}}]{sub_field}

【硬性要求】
1. 每条场景必须具体：含背景、约束、可选动作，像真实用户的求助输入；
2. 各条之间在领域、时间尺度、资源约束上尽量分散，不得雷同；
3. 只输出 JSON 数组本身，不要 markdown 代码块、不要解释。"""


def parse_json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # 容错：截取第一个 [ 到最后一个 ]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("输出中未找到 JSON 数组")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("JSON 顶层不是数组")
    return data


def normalize(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:\"'“”‘’（）()]", "", text)


def validate_item(item: dict, cfg: dict, existing_norms: set) -> tuple[bool, str]:
    if not isinstance(item, dict):
        return False, "非对象元素"
    scenario = str(item.get("scenario") or "").strip()
    if not scenario:
        return False, "空场景"
    if len(scenario) < 8 or len(scenario) > 500:
        return False, f"长度异常({len(scenario)})"
    norm = normalize(scenario)
    if norm in existing_norms:
        return False, "重复"
    # 回路预判校验：生成的场景必须触发预期的回路
    actual_loop = "fast" if local_is_fast_loop(scenario) else "slow"
    if actual_loop != cfg["expected_loop"]:
        return False, f"回路不符(预期{cfg['expected_loop']}/实际{actual_loop})"
    return True, scenario


def generate_category(key: str, cfg: dict, limit: int | None = None, batch_size: int = 8) -> dict:
    target = limit or cfg["target"]
    test_storage.init_test_db()

    existing = test_storage.get_scenarios(category=key)
    existing_norms = {normalize(s["scenario_text"]) for s in existing}
    existing_texts_norm_global = {normalize(s["scenario_text"]) for s in test_storage.get_scenarios()}
    existing_norms |= existing_texts_norm_global

    collected: list[dict] = []
    attempts, max_attempts = 0, 8
    while len(collected) < target and attempts < max_attempts:
        attempts += 1
        want = min(batch_size, target - len(collected) + 2)  # 多要2条抵御丢弃
        try:
            raw = chat(SYS_PROMPT, build_prompt(key, cfg, want),
                       temperature=0.9, max_tokens=4096)
            items = parse_json_array(raw)
        except Exception as e:
            print(f"  [第{attempts}次] 调用/解析失败: {e}")
            continue
        dropped = 0
        for it in items:
            if len(collected) >= target:
                break
            ok, info = validate_item(it, cfg, existing_norms)
            if not ok:
                dropped += 1
                continue
            existing_norms.add(normalize(info))
            collected.append({"subcategory": (it.get("subcategory") or cfg["name"]).strip(),
                              "scenario": info})
        print(f"  [第{attempts}次] 获得 {len(collected)}/{target}（丢弃 {dropped} 条）")

    inserted = 0
    for c in collected:
        test_storage.insert_scenario(
            category=key, subcategory=c["subcategory"],
            scenario_text=c["scenario"], expected_loop=cfg["expected_loop"],
            source="deepseek_generated",
        )
        inserted += 1
    return {"category": key, "requested": target, "inserted": inserted,
            "attempts": attempts, "reached": len(collected) >= target}


def main():
    parser = argparse.ArgumentParser(description="批量生成决策测试场景")
    parser.add_argument("--category", choices=list(CATEGORIES.keys()), default=None,
                        help="只生成指定类别（默认全部）")
    parser.add_argument("--limit", type=int, default=None,
                        help="每个类别生成数量上限（试跑用，覆盖默认目标）")
    parser.add_argument("--list", action="store_true", help="列出所有类别后退出")
    args = parser.parse_args()

    if args.list:
        total = 0
        for k, c in CATEGORIES.items():
            print(f"  {k:24s} {c['name']:12s} 目标 {c['target']:3d} 条  预期回路 {c['expected_loop']}")
            total += c["target"]
        print(f"  {'合计':24s} {'':12s} {total:3d} 条")
        return

    keys = [args.category] if args.category else list(CATEGORIES.keys())
    results = []
    for k in keys:
        cfg = CATEGORIES[k]
        print(f"\n=== 生成类别 {k}（{cfg['name']}），目标 {args.limit or cfg['target']} 条 ===")
        results.append(generate_category(k, cfg, limit=args.limit))

    print("\n===== 生成汇总 =====")
    for r in results:
        mark = "OK" if r["reached"] else "未达标"
        print(f"  {r['category']:24s} 入库 {r['inserted']:3d}/{r['requested']:3d}  [{mark}]")
    stats = test_storage.get_review_stats()
    print(f"\n当前库内场景总数: {stats['total']}")


if __name__ == "__main__":
    main()
