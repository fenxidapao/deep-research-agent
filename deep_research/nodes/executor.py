"""Executor 节点：用 smolagents CodeAgent 执行当前步骤的研究。

CodeAgent 是"代码执行式"agent：它会自己写 Python 代码调用搜索/抓取工具，
比纯工具调用式 agent 更灵活（可循环、可组合、可分析中间结果）。

`run_single_step` 为公共单步执行函数：Executor（单步）与 Supervisor（并行分发）
共用同一执行逻辑，保证两种模式行为一致。
"""

from typing import Any, Optional

from smolagents import CodeAgent

from ..config import Config
from ..logging_utils import get_logger
from ..memory import ExperienceMemory
from ..state import ResearchState
from ..tools import build_search_tools

logger = get_logger("executor")

EXECUTOR_TASK_TEMPLATE = """你是研究执行员，正在为一份深度研究报告收集资料。

## 调研总目标（research_brief）
{research_brief}

## 当前步骤（只做这一步）
{step_description}

## 建议的搜索关键词（可以自行调整）
{queries}

## 工作方式
1. 用 web_search 搜索相关关键词（必要时多轮，注意换词避免重复）。
2. 对高价值网页用 fetch_page 抓取正文，提取关键事实和数据。
3. 你可以写 Python 代码处理搜索结果（去重、提取数字等）。

## 输出要求（最终回答必须是以下格式）
研究笔记：
- 核心事实与数据（尽量具体，含时间、数字）
- 关键来源（链接）
- 未能查证的内容（明确标注）
字数控制在 300~600 字，使用中文。"""


def run_single_step(
    cfg: Config,
    counter,
    research_brief: str,
    task: str,
    step: dict,
    search_history: list[str],
    memory: Optional[ExperienceMemory] = None,
) -> tuple[str, list[str]]:
    """执行单步研究，返回 (研究笔记, 本轮实际建议查询词)。

    - 内部捕获所有异常并沉淀经验（若传入 memory），保证调用方（含并行 worker）不中断；
    - fresh_queries 用于累计 search_history，防下一轮重复搜索。
    """
    from ..model import build_model

    queries = step.get("queries", [])
    prompt = EXECUTOR_TASK_TEMPLATE.format(
        research_brief=research_brief,
        step_description=step["description"],
        queries="、".join(queries) if queries else "（无，自行设计）",
    )
    fresh_queries = [q for q in queries if q not in search_history]

    try:
        model = build_model(cfg, counter)
        agent = CodeAgent(
            tools=build_search_tools(cfg.search_provider, cfg.tavily_api_key),
            model=model,
            max_steps=cfg.max_searches_per_step + 5,
            # Bing 单次搜索约 11s，默认 30s 代码执行超时远不够，放宽到 180s
            executor_kwargs={"timeout_seconds": 180},
            verbosity_level=0,
        )
        note = agent.run(prompt)
        if not isinstance(note, str) or not note.strip():
            note = f"（步骤 {step['id']} 未产出有效笔记）"
    except Exception as e:  # noqa: BLE001
        logger.error("步骤 %d 执行失败: %s: %s", step["id"], type(e).__name__, e)
        note = f"（步骤 {step['id']} 执行失败：{type(e).__name__}: {e}。可由 Reflector 决定重规划或跳过）"
        if memory is not None:
            memory.add(
                domain=str(task)[:50],
                lesson=f"步骤{step['id']}执行失败: {type(e).__name__}: {str(e)[:120]}",
                suggestion="换更具体的关键词、拆分任务或降级搜索源后重试",
            )
    return note, fresh_queries


def executor_node(cfg: Config, counter=None):
    """返回 Executor 节点函数（闭包注入配置，单步串行执行）。"""

    memory = ExperienceMemory(cfg.memory_file)

    def node(state: ResearchState) -> dict[str, Any]:
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        if idx >= len(plan):
            return {"status": "complete"}

        step = plan[idx]
        logger.info("执行步骤 %d/%d: %s", idx + 1, len(plan), step["description"][:60])
        note, fresh_queries = run_single_step(
            cfg,
            counter,
            state.get("research_brief", state["task"]),
            state["task"],
            step,
            state.get("search_history", []),
            memory,
        )

        return {
            "current_step": idx + 1,
            "completed_steps": [f"步骤{step['id']}: {step['description']}"],
            "intermediate_results": [f"【步骤{step['id']}】{note}"],
            "search_history": fresh_queries,  # 记录本轮实际建议查询词，防下一轮重复
        }

    return node
