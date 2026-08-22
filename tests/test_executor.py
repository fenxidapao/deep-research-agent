"""Executor 集成测试：验证 CourseRAG 工具挂载 + 提示词引导（全 mock，不碰网络）。"""

from deep_research.config import Config
from deep_research.nodes.executor import EXECUTOR_TASK_TEMPLATE, run_single_step
from deep_research.tools import CourseRetrieveTool, FetchPageTool, WebSearchTool

from .helpers import FakeModel


class _FakeAgent:
    """假 CodeAgent：捕获构造参数，run 返回固定笔记。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.tools = kwargs["tools"]

    def run(self, prompt):
        self.prompt = prompt
        return "模拟研究笔记：红黑树性质已查证。"


def test_executor_attaches_course_retrieve_tool(monkeypatch):
    captured = {}

    def fake_agent_factory(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeAgent(**kwargs)

    monkeypatch.setattr("deep_research.nodes.executor.CodeAgent", fake_agent_factory)
    monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: FakeModel([]))

    cfg = Config(rag_base_url="http://127.0.0.1:8001", rag_top_k=3, rag_timeout=15)
    note, fresh = run_single_step(
        cfg,
        None,
        "调研红黑树",
        "红黑树是什么",
        {"id": 1, "description": "查红黑树定义与性质", "queries": ["红黑树"]},
        [],
    )

    assert note == "模拟研究笔记：红黑树性质已查证。"
    assert fresh == ["红黑树"]
    tools = captured["kwargs"]["tools"]
    types = [type(t) for t in tools]
    assert WebSearchTool in types and FetchPageTool in types and CourseRetrieveTool in types

    cr = [t for t in tools if isinstance(t, CourseRetrieveTool)][0]
    assert cr.base_url == "http://127.0.0.1:8001"
    assert cr.top_k == 3
    assert cr.timeout == 15


def test_executor_skips_tool_when_no_rag_url(monkeypatch):
    captured = {}

    def fake_agent_factory(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeAgent(**kwargs)

    monkeypatch.setattr("deep_research.nodes.executor.CodeAgent", fake_agent_factory)
    monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: FakeModel([]))

    cfg = Config(rag_base_url="")  # 未配置 RAG → 不挂工具
    run_single_step(
        cfg,
        None,
        "调研",
        "任务",
        {"id": 1, "description": "搜索", "queries": []},
        [],
    )
    tools = captured["kwargs"]["tools"]
    assert not any(isinstance(t, CourseRetrieveTool) for t in tools)


def test_executor_prompt_guides_course_retrieve():
    """提示词必须引导 CodeAgent 优先使用课程库（面试/代码可查证）。"""
    assert "course_retrieve" in EXECUTOR_TASK_TEMPLATE
    assert "课程知识库" in EXECUTOR_TASK_TEMPLATE
