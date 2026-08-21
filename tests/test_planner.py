"""Planner 相关测试：_extract_json 容错 + 输出异常时的兜底。"""

import json

import pytest

from deep_research.config import Config
from deep_research.nodes.planner import _extract_json, planner_node

from .helpers import FakeModel


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert _extract_json('```json\n{"steps": []}\n```') == {"steps": []}

    def test_fence_without_lang(self):
        assert _extract_json('```\n{"x": "y"}\n```') == {"x": "y"}

    def test_surrounding_chatter(self):
        text = '好的，这是调研计划：\n{"research_brief": "简报", "steps": []}\n希望对你有帮助'
        assert _extract_json(text)["research_brief"] == "简报"

    def test_nested_braces(self):
        text = '{"steps": [{"id": 1, "queries": ["a", "b"]}]}'
        data = _extract_json(text)
        assert data["steps"][0]["queries"] == ["a", "b"]

    def test_no_braces_raises(self):
        with pytest.raises(ValueError):
            _extract_json("输出里完全没有 JSON 对象")

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json('{"a": }')


class TestPlannerFallback:
    def test_empty_output_falls_back(self, monkeypatch):
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: FakeModel([""]))
        node = planner_node(Config())
        out = node({"task": "测试任务"})
        assert len(out["plan"]) == 1
        assert out["status"] == "running"
        assert "兜底" in out["reflection"]
        assert out["plan"][0]["queries"] == ["测试任务"]

    def test_non_json_output_falls_back(self, monkeypatch):
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: FakeModel(["这不是JSON，只是普通文本"]))
        node = planner_node(Config())
        out = node({"task": "测试任务"})
        assert len(out["plan"]) == 1
        assert out["status"] == "running"

    def test_valid_plan_parsed(self, monkeypatch):
        payload = json.dumps(
            {
                "research_brief": "调研简报",
                "steps": [
                    {"id": 1, "description": "第一步", "queries": ["关键词A"]},
                    {"id": 2, "description": "第二步", "queries": ["关键词B", "关键词C"]},
                ],
            },
            ensure_ascii=False,
        )
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: FakeModel([payload]))
        node = planner_node(Config())
        out = node({"task": "测试任务"})
        assert out["research_brief"] == "调研简报"
        assert len(out["plan"]) == 2
        assert out["plan"][1]["queries"] == ["关键词B", "关键词C"]
        assert out["current_step"] == 0

    def test_planner_injects_experiences(self, monkeypatch, tmp_path):
        """经验闭环的读取端：历史经验应注入首次规划的用户提示词。"""
        from deep_research.memory import ExperienceMemory

        exp = ExperienceMemory(str(tmp_path / "exp.json"))
        exp.add("测试任务", "关键词太宽导致结果泛化", "拆成具体子词")

        payload = json.dumps(
            {"research_brief": "简报", "steps": [{"id": 1, "description": "第一步", "queries": ["q"]}]},
            ensure_ascii=False,
        )
        fake = FakeModel([payload])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = planner_node(Config(memory_file=str(exp.path)))
        node({"task": "测试任务"})

        user_msg = fake.messages[0][1]["content"]  # [0]=system, [1]=user
        assert "历史经验" in user_msg
        assert "关键词太宽" in user_msg
        assert "拆成具体子词" in user_msg

    def test_planner_no_experience_no_injection(self, monkeypatch, tmp_path):
        """无相关经验时提示词不含历史经验块。"""
        payload = json.dumps(
            {"research_brief": "简报", "steps": [{"id": 1, "description": "第一步", "queries": ["q"]}]},
            ensure_ascii=False,
        )
        fake = FakeModel([payload])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = planner_node(Config(memory_file=str(tmp_path / "empty.json")))
        node({"task": "测试任务"})

        user_msg = fake.messages[0][1]["content"]
        assert "历史经验" not in user_msg
