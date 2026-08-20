"""deep_research 包：LangGraph 编排 + smolagents 内核的深度研究 Agent。

参考 open_deep_research 的规划-反思思路，但：
- 编排层：LangGraph 显式三节点（Planner / Executor / Reflector）+ 条件边回环
- 执行层：smolagents CodeAgent（代码执行式工具调用）
- 模型：DeepSeek API 为主，Ollama 本地降级
"""

from .config import Config, get_config
from .graph import build_graph

__all__ = ["Config", "get_config", "build_graph"]
__version__ = "0.1.0"
