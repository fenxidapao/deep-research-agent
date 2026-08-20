"""Graph 组装：Planner → Executor → Reflector ⇄（continue/replan）→ Writer → END。

条件路由：
- Reflector 判定 continue → 回到 Executor 执行下一步
- Reflector 判定 replan  → 回到 Planner 基于已有进展重规划
- Reflector 判定 complete → 进入 Writer 写最终报告
"""

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .config import Config
from .nodes.executor import executor_node
from .nodes.planner import planner_node
from .nodes.reflector import reflector_node
from .nodes.writer import writer_node
from .state import ResearchState


def _route(state: ResearchState) -> str:
    """Reflector 之后的条件路由。"""
    status = state.get("status", "running")
    if status == "complete":
        return "writer"
    if status == "replan":
        return "planner"
    return "executor"


def build_graph(cfg: Config):
    """构建并编译可编译的 LangGraph（含 MemorySaver 断点续跑）。"""
    graph = StateGraph(ResearchState)

    graph.add_node("planner", planner_node(cfg))
    graph.add_node("executor", executor_node(cfg))
    graph.add_node("reflector", reflector_node(cfg))
    graph.add_node("writer", writer_node(cfg))

    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reflector")
    graph.add_conditional_edges("reflector", _route, {"executor": "executor", "planner": "planner", "writer": "writer"})
    graph.add_edge("writer", END)

    # MemorySaver：支持断点续跑（thread_id 维度）
    return graph.compile(checkpointer=MemorySaver())
