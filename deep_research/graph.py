"""Graph 组装：Planner → Executor → Reflector ⇄（continue/replan）→ Writer → END。

条件路由：
- Reflector 判定 continue → 回到 Executor 执行下一步
- Reflector 判定 replan  → 回到 Planner 基于已有进展重规划
- Reflector 判定 complete → 进入 Writer 写最终报告

对照实验（ablation）：
- reflect=True  （默认）：Reflector 调用模型做语义判定（有反思）
- reflect=False ：顺序执行所有计划步骤后收尾，不调用模型判定（无反思）
  用于量化"反思"对答案质量的提升。
"""

from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .config import Config
from .model import UsageCounter
from .nodes.executor import executor_node
from .nodes.planner import planner_node
from .nodes.reflector import reflector_node
from .nodes.supervisor import supervisor_node
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


def _sequential_reflector_node(cfg: Config):
    """无反思版 Reflector：不调用模型，顺序执行完所有计划步骤后收尾。"""

    def node(state: ResearchState) -> dict[str, Any]:
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        done = len(plan) > 0 and idx >= len(plan)
        return {
            "reflection": "（无反思模式：顺序执行计划步骤）",
            "iteration": state.get("iteration", 0) + 1,
            "status": "complete" if done else "running",
        }

    return node


def build_graph(cfg: Config, reflect: bool = True, supervisor: bool = False, counter: Optional[UsageCounter] = None):
    """构建并编译 LangGraph（含 MemorySaver 断点续跑 + token 计数）。

    reflect=False 时启用无反思对照版（用于"反思前后对比"评测）。
    supervisor=True 时用 Supervisor 节点替代 Executor：一批步骤并行分发给多个 worker。
    编译后的图对象带有 .usage_counter 属性（UsageCounter），可读取累计 token。
    """
    counter = counter or UsageCounter()
    reflect_node = reflector_node(cfg, counter) if reflect else _sequential_reflector_node(cfg)
    exec_node = supervisor_node(cfg, counter) if supervisor else executor_node(cfg, counter)

    graph = StateGraph(ResearchState)

    graph.add_node("planner", planner_node(cfg, counter))
    graph.add_node("executor", exec_node)
    graph.add_node("reflector", reflect_node)
    graph.add_node("writer", writer_node(cfg, counter))

    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reflector")
    graph.add_conditional_edges("reflector", _route, {"executor": "executor", "planner": "planner", "writer": "writer"})
    graph.add_edge("writer", END)

    compiled = graph.compile(checkpointer=MemorySaver())
    compiled.usage_counter = counter  # 供评测脚本统计 token
    return compiled
