"""Reflector 节点：评估研究进度，决定 continue / replan / complete。"""

import json
from typing import Any

from ..config import Config
from ..prompts import REFLECTOR_SYSTEM_PROMPT, TODAY
from ..state import ResearchState
from .planner import _extract_json

DECISION_MAP = {"continue": "running", "replan": "replan", "complete": "complete"}


def reflector_node(cfg: Config):
    """返回 Reflector 节点函数（闭包注入配置）。"""

    def node(state: ResearchState) -> dict[str, Any]:
        from ..model import build_model

        iteration = state.get("iteration", 0)
        plan = state.get("plan", [])
        done = state.get("completed_steps", [])
        results = state.get("intermediate_results", [])

        # ---- 硬性退出条件：预算用尽或步骤全部执行完 ----
        forced_complete = False
        if iteration >= cfg.max_iterations:
            forced_complete = True
            reason = f"已达最大循环轮数 {cfg.max_iterations}，强制收尾"
        elif state.get("current_step", 0) >= len(plan) and plan:
            forced_complete = True
            reason = "计划内步骤已全部执行，进入收尾"
        elif not plan:
            forced_complete = True
            reason = "计划为空，无法继续"

        if forced_complete:
            return {
                "reflection": reason,
                "iteration": iteration + 1,
                "status": "complete",
            }

        # ---- 调用模型做语义判定 ----
        model = build_model(cfg)
        remaining = plan[state.get("current_step", 0) :]
        remaining_desc = "\n".join(f"- 步骤{s['id']}: {s['description']}" for s in remaining)

        context = (
            f"调研简报：{state.get('research_brief', state['task'])}\n\n"
            f"已完成 {len(done)}/{len(plan)} 步：\n" + "\n".join(done) + "\n\n"
            f"研究笔记摘要：\n" + "\n\n".join(results[-3:]) + "\n\n"
            f"剩余步骤：\n{remaining_desc}"
        )

        prompt = REFLECTOR_SYSTEM_PROMPT.format(today=TODAY, max_iterations=cfg.max_iterations)
        raw = model([{"role": "system", "content": prompt}, {"role": "user", "content": context}]).content

        try:
            data = _extract_json(raw)
            decision = str(data.get("decision", "continue")).strip().lower()
            if decision not in DECISION_MAP:
                decision = "continue"
        except Exception as e:  # noqa: BLE001
            decision = "continue"
            data = {"reason": f"反思解析失败，默认继续: {e}", "gap": ""}

        return {
            "reflection": f"决策={decision} | 理由: {data.get('reason', '')} | 缺口: {data.get('gap', '')}",
            "iteration": iteration + 1,
            "status": DECISION_MAP[decision],
        }

    return node
