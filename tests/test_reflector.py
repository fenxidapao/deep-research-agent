"""Reflector 节点测试：硬性退出条件（预算护栏）+ 决策解析。"""

import json

from deep_research.config import Config
from deep_research.nodes.reflector import reflector_node

from .helpers import FakeModel


def _cfg(**kw) -> Config:
    params = {"max_iterations": 4}
    params.update(kw)
    return Config(**params)


class TestForcedComplete:
    """硬性退出条件：不调用模型，直接收尾（护栏）。"""

    def test_max_iterations_forces_complete(self, monkeypatch):
        fake = FakeModel([])  # 不应被调用
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                    "current_step": 0, "iteration": 4})  # iteration 达到上限
        assert out["status"] == "complete"
        assert fake.calls == 0  # 模型未被调用

    def test_all_plan_steps_done_forces_complete(self, monkeypatch):
        fake = FakeModel([])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                    "current_step": 1, "iteration": 1})  # 步骤已全部执行
        assert out["status"] == "complete"
        assert fake.calls == 0

    def test_empty_plan_forces_complete(self, monkeypatch):
        fake = FakeModel([])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [], "current_step": 0, "iteration": 0})
        assert out["status"] == "complete"

    def test_replan_chain_reaches_guard(self, monkeypatch):
        """连续 replan 时 iteration 正确累计，最终被 max_iterations 护栏截停（缺陷修复的闭环验证）。"""
        replan = json.dumps({"decision": "replan", "reason": "缺资料", "gap": ""}, ensure_ascii=False)
        fake = FakeModel([replan, replan, replan, replan, replan])  # 模型一直要求 replan
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)

        node = reflector_node(_cfg(max_iterations=3))
        iteration = 0
        status = "running"
        for _ in range(6):  # 即使模型一直 replan，最多 3 轮后强制收尾
            out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                        "current_step": 0, "iteration": iteration})
            iteration = out["iteration"]
            status = out["status"]
            if status != "replan":
                break
        assert status == "complete"
        # iteration 语义：每次节点运行 +1。3 轮模型判定（输入 0/1/2）+ 第 4 次输入 3 触发护栏强制收尾
        assert iteration == 4
        # 模型实际只被调用 3 次（第 4 次走护栏，未调模型）
        assert fake.calls == 3


class TestDecisionParsing:
    def test_replan_decision(self, monkeypatch):
        payload = json.dumps({"decision": "replan", "reason": "缺关键数据", "gap": "权威来源"}, ensure_ascii=False)
        fake = FakeModel([payload])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                    "current_step": 0, "iteration": 0})
        assert out["status"] == "replan"
        assert out["iteration"] == 1

    def test_complete_decision(self, monkeypatch):
        payload = json.dumps({"decision": "complete", "reason": "资料足够", "gap": ""}, ensure_ascii=False)
        fake = FakeModel([payload])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                    "current_step": 1, "iteration": 0, "completed_steps": ["步骤1"]})  # 已执行过步骤
        assert out["status"] == "complete"

    def test_complete_with_zero_steps_downgraded(self, monkeypatch):
        """P-1 护栏：计划非空却一步未执行就判定 complete → 强制 continue。"""
        payload = json.dumps({"decision": "complete", "reason": "信息足够", "gap": ""}, ensure_ascii=False)
        fake = FakeModel([payload])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                    "current_step": 0, "iteration": 0})  # 无 completed_steps
        assert out["status"] == "running"  # 护栏降级为 continue
        assert "护栏" in out["reflection"]

    def test_invalid_decision_defaults_continue(self, monkeypatch):
        payload = json.dumps({"decision": "whatever", "reason": "", "gap": ""}, ensure_ascii=False)
        fake = FakeModel([payload])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                    "current_step": 0, "iteration": 0})
        assert out["status"] == "running"

    def test_bad_json_defaults_continue(self, monkeypatch):
        fake = FakeModel(["不是JSON"])
        monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
        node = reflector_node(_cfg())
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}],
                    "current_step": 0, "iteration": 0})
        assert out["status"] == "running"  # 解析失败默认继续，不中断流程
