"""Writer 节点测试：DeepSeek 偶发空输出的重试 + 兜底逻辑（HANDOVER 踩坑 #5）。"""

from deep_research.config import Config
from deep_research.nodes.writer import writer_node

from .helpers import FakeModel

VALID_REPORT = "这是一份足够长的测试报告内容。" * 10  # >50 字符

STATE = {
    "task": "测试任务",
    "research_brief": "调研简报",
    "intermediate_results": ["【步骤1】笔记A", "【步骤2】笔记B"],
}


def _make_node(monkeypatch, fake):
    monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
    return writer_node(Config())


def test_empty_output_retries_then_falls_back(monkeypatch):
    fake = FakeModel(["", "", ""])  # 三次都空 → 触发兜底
    out = _make_node(monkeypatch, fake)(dict(STATE))
    assert out["status"] == "complete"
    assert "研究笔记原文" in out["final_report"]
    assert "笔记A" in out["final_report"]
    assert fake.responses == []  # 三次重试用完


def test_short_output_retries(monkeypatch):
    fake = FakeModel(["太短了", VALID_REPORT])
    out = _make_node(monkeypatch, fake)(dict(STATE))
    assert out["final_report"].startswith("这是一份足够长")


def test_first_valid_output_used(monkeypatch):
    fake = FakeModel([VALID_REPORT])
    out = _make_node(monkeypatch, fake)(dict(STATE))
    assert out["final_report"].startswith("这是一份足够长")
    assert fake.responses == []  # 只调用了一次


def test_no_notes_uses_placeholder(monkeypatch):
    fake = FakeModel(["", "", ""])
    state = {"task": "测试任务", "intermediate_results": []}
    out = _make_node(monkeypatch, fake)(state)
    assert "未收集到研究笔记" in out["final_report"]
