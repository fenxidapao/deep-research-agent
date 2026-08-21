"""Planner 节点：把用户任务拆解为调研简报 + 步骤列表。"""

import json
import re
from typing import Any

from ..config import Config
from ..logging_utils import get_logger
from ..memory import ExperienceMemory
from ..prompts import PLANNER_SYSTEM_PROMPT, TODAY
from ..state import PlanStep, ResearchState

logger = get_logger("planner")


def _extract_json(text: str) -> dict[str, Any]:
    """从模型输出中稳健提取 JSON（容忍代码块包裹 / 前后杂质）。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"输出中未找到 JSON 对象: {text[:200]}")
    return json.loads(text[start : end + 1])


def _as_model(cfg: Config, counter=None):
    """延迟导入避免循环依赖。"""
    from ..model import build_model

    return build_model(cfg, counter)


def planner_node(cfg: Config, counter=None):
    """返回 Planner 节点函数（闭包注入配置）。

    首次规划：基于用户任务拆解，并注入历史经验（避免重蹈覆辙）。
    重规划（Reflector 判定 replan 后）：基于已有研究进展调整计划，避免重复劳动。
    """
    memory = ExperienceMemory(cfg.memory_file)

    def node(state: ResearchState) -> dict[str, Any]:
        model = _as_model(cfg, counter)
        prompt = PLANNER_SYSTEM_PROMPT.format(today=TODAY, max_steps=cfg.max_plan_steps)

        # 重规划场景：带上已有进展，要求新计划基于现状调整
        existing = state.get("intermediate_results", [])
        if existing:
            logger.info("重规划: 已有 %d 条研究笔记", len(existing))
            user_msg = (
                f"用户任务：\n{state['task']}\n\n"
                f"原调研简报：{state.get('research_brief', state['task'])}\n\n"
                f"已有研究进展（不可重复调研）：\n" + "\n\n".join(existing) + "\n\n"
                f"请基于已有进展**重新规划**剩余步骤：只列出仍需调研的维度，跳过已完成内容。"
            )
        else:
            logger.info("首次规划: %s", state["task"][:80])
            user_msg = f"用户任务：\n{state['task']}\n\n请给出调研简报与步骤拆解。"
            # 注入历史经验，避免同类任务重蹈覆辙（无相关经验时不影响提示词）
            experiences = memory.relevant(state["task"])
            if experiences:
                lines = "\n".join(
                    f"- {e.get('lesson', '')} → 建议：{e.get('suggestion', '')}" for e in experiences
                )
                user_msg += f"\n\n【历史经验（来自同类任务，规划时注意规避）】\n{lines}"

        raw = model([{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}]).content

        # 模型输出异常（空/非 JSON）时兜底为单步计划，避免整条流程崩溃
        try:
            data = _extract_json(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("Planner 输出解析失败，兜底为单步计划: %s", e)
            fallback_desc = "围绕调研主题进行全面的网络搜索与资料整理"
            return {
                "research_brief": state.get("research_brief", state["task"]),
                "plan": [{"id": 1, "description": fallback_desc, "queries": [state["task"]]}],
                "current_step": 0,
                # 保留 iteration：重规划时若重置为 0，max_iterations 护栏会失效（曾为缺陷）
                "iteration": state.get("iteration", 0),
                "status": "running",
                "reflection": f"Planner 输出解析失败已兜底: {e}",
            }

        steps: list[PlanStep] = []
        for i, s in enumerate(data.get("steps", []), 1):
            steps.append(
                {
                    "id": int(s.get("id", i)),
                    "description": str(s.get("description", "")),
                    "queries": [str(q) for q in s.get("queries", [])],
                }
            )

        return {
            "research_brief": str(data.get("research_brief", state["task"])),
            "plan": steps,
            "current_step": 0,
            # 首次规划 state 无 iteration → 0；重规划保留 Reflector 累计值，护栏才生效
            "iteration": state.get("iteration", 0),
            "status": "running",
        }

    return node
