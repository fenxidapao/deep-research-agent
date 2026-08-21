"""Supervisor 节点：把待执行步骤分批分发给多个 worker 并行研究。

架构（浅层 Multi-Agent）：
Planner 拆解步骤 → Supervisor 取一批步骤（≤ max_parallel_workers）→
ThreadPoolExecutor 并行跑多个 worker（各自独立 CodeAgent）→ 汇总笔记 →
Reflector 照常评估是否继续/重规划/收尾。

设计要点：
- worker 复用 `run_single_step`（与单步 Executor 同逻辑），行为一致；
- 单 worker 失败不影响其他（内部已捕获异常并沉淀经验）；
- 并发安全：UsageCounter / ExperienceMemory 内部有锁。
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from ..config import Config
from ..logging_utils import get_logger
from ..memory import ExperienceMemory
from ..state import ResearchState
from .executor import run_single_step

logger = get_logger("supervisor")


def supervisor_node(cfg: Config, counter=None):
    """返回 Supervisor 节点函数（闭包注入配置，一批步骤并行分发）。"""

    memory = ExperienceMemory(cfg.memory_file)
    max_workers = max(1, cfg.max_parallel_workers)

    def _run_batch(state: ResearchState, batch: list[dict]) -> list[tuple[dict, str, list[str]]]:
        """并行执行一批步骤，返回 [(step, note, fresh_queries)]（保持输入顺序）。"""
        brief = state.get("research_brief", state["task"])
        task = state["task"]
        history = list(state.get("search_history", []))

        def work(step: dict) -> tuple[dict, str, list[str]]:
            # run_single_step 内部已捕获异常；此处再兜底一层，防未来改动漏捕获拖垮整批
            try:
                note, fresh = run_single_step(cfg, counter, brief, task, step, history, memory)
            except Exception as e:  # noqa: BLE001
                logger.error("worker 步骤 %d 异常: %s", step.get("id"), e)
                note = f"（步骤 {step.get('id')} 执行异常：{type(e).__name__}: {e}）"
                fresh = []
            return step, note, fresh

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(work, batch))

    def node(state: ResearchState) -> dict[str, Any]:
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        if idx >= len(plan):
            return {"status": "complete"}

        batch = plan[idx : idx + max_workers]
        logger.info(
            "supervisor 分发 %d/%d 步（并行 %d）: %s",
            len(batch), len(plan), max_workers,
            "、".join(s["description"][:20] for s in batch),
        )

        results = _run_batch(state, batch)
        completed = [f"步骤{s['id']}: {s['description']}" for s, _, _ in results]
        notes = [f"【步骤{s['id']}】{note}" for s, note, _ in results]
        all_fresh = [q for _, _, fresh in results for q in fresh]

        return {
            "current_step": idx + len(batch),  # 一次推进整批
            "completed_steps": completed,
            "intermediate_results": notes,
            "search_history": all_fresh,
        }

    return node
