"""提示词安全回归测试：注入防护指令必须存在于各节点提示词中（防未来改动删除）。"""

from deep_research.nodes.executor import EXECUTOR_TASK_TEMPLATE
from deep_research.prompts import (
    PLANNER_SYSTEM_PROMPT,
    REFLECTOR_SYSTEM_PROMPT,
    WRITER_SYSTEM_PROMPT,
)

_GUARD_MARKERS = ("忽略", "注入")


def test_planner_has_injection_guard():
    assert all(m in PLANNER_SYSTEM_PROMPT for m in _GUARD_MARKERS)
    assert "系统提示词" in PLANNER_SYSTEM_PROMPT


def test_reflector_has_injection_guard():
    assert all(m in REFLECTOR_SYSTEM_PROMPT for m in _GUARD_MARKERS)
    assert "系统提示词" in REFLECTOR_SYSTEM_PROMPT


def test_writer_has_injection_guard():
    assert all(m in WRITER_SYSTEM_PROMPT for m in _GUARD_MARKERS)
    assert "系统提示词" in WRITER_SYSTEM_PROMPT


def test_executor_has_injection_guard_and_tool_guidance():
    assert all(m in EXECUTOR_TASK_TEMPLATE for m in _GUARD_MARKERS)
    assert "fetch_page" in EXECUTOR_TASK_TEMPLATE
    # 禁止直接 import 网络库（日志证据：agent 尝试 urllib 被沙箱拒绝导致 max_steps 触顶）
    assert "urllib" in EXECUTOR_TASK_TEMPLATE
    assert "禁止在代码里 import" in EXECUTOR_TASK_TEMPLATE
