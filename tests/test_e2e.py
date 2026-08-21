"""端到端集成测试：真实 LangGraph 图 + mock 模型/执行器，不调任何真实 API 与网络。

流程验证：Planner → Executor → Reflector → Writer → END，状态累加与条件路由正确。
（使用 reflect=False 无反思模式：Reflector 不做语义判定，整图只有 Planner/Writer 各调一次模型）
"""

import json

from deep_research import build_graph
from deep_research.config import Config

from .helpers import FakeModel

PLAN_JSON = json.dumps(
    {
        "research_brief": "测试调研简报",
        "steps": [
            {"id": 1, "description": "搜索背景资料", "queries": ["关键词A"]},
            {"id": 2, "description": "核查关键数据", "queries": ["关键词B"]},
        ],
    },
    ensure_ascii=False,
)

REPORT = "这是一份端到端测试生成的完整研究报告。" * 20


def _fake_executor_factory(cfg, counter=None):
    """假 Executor：不实例化 CodeAgent，直接产出固定研究笔记。"""

    def node(state):
        idx = state.get("current_step", 0)
        step = state["plan"][idx]
        return {
            "current_step": idx + 1,
            "completed_steps": [f"步骤{step['id']}: {step['description']}"],
            "intermediate_results": [f"【步骤{step['id']}】模拟研究笔记：{step['description']}"],
            "search_history": step.get("queries", []),
        }

    return node


def test_end_to_end_mocked(monkeypatch):
    fake = FakeModel([PLAN_JSON, REPORT])
    monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
    # graph.py 顶部 import 已绑定名字，必须 patch graph 模块里的引用
    monkeypatch.setattr("deep_research.graph.executor_node", _fake_executor_factory)

    graph = build_graph(Config(), reflect=False)
    final = graph.invoke(
        {"task": "测试任务"},
        config={"configurable": {"thread_id": "test-e2e-basic"}},
    )

    assert final["status"] == "complete"
    assert final["final_report"].startswith("这是一份端到端测试")
    assert fake.calls == 2  # planner + writer 各一次
    # 两条计划步骤都执行完（状态累加正确）
    assert len(final["completed_steps"]) == 2
    assert len(final["intermediate_results"]) == 2
    assert final["search_history"] == ["关键词A", "关键词B"]


def test_end_to_end_replan_routing(monkeypatch):
    """Reflector 语义判定 replan → 回 Planner 重规划 → 再次执行 → complete。

    通过模型调用次数验证 replan 循环真实发生：
    planner×2（首规划+重规划）+ reflector×2（replan+complete）+ writer×1 = 5 次。
    注意：iteration 计数被 planner 重置（既有缺陷，见 HANDOVER 遗留项），不能用来断言循环次数。
    """
    replan_json = json.dumps({"decision": "replan", "reason": "需要补充", "gap": "缺数据"}, ensure_ascii=False)
    complete_json = json.dumps({"decision": "complete", "reason": "资料足够", "gap": ""}, ensure_ascii=False)

    # 调用顺序：planner(计划) → reflector(replan) → planner(重规划) → reflector(complete) → writer(报告)
    responses = [PLAN_JSON, replan_json, PLAN_JSON, complete_json, REPORT]
    fake = FakeModel(responses)
    monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
    # graph.py 顶部 import 已绑定名字，必须 patch graph 模块里的引用
    monkeypatch.setattr("deep_research.graph.executor_node", _fake_executor_factory)

    graph = build_graph(Config(), reflect=True)
    final = graph.invoke(
        {"task": "测试任务"},
        config={"configurable": {"thread_id": "test-e2e-replan"}},
    )

    assert final["status"] == "complete"
    assert final["final_report"].startswith("这是一份端到端测试")
    assert fake.calls == 5  # replan 循环真实发生


def test_end_to_end_supervisor_mode(monkeypatch):
    """supervisor 模式全链路：并行分发一批步骤 → 汇总 → 报告。"""
    fake = FakeModel([PLAN_JSON, REPORT])

    def fake_run(cfg, counter, brief, task, step, history, memory=None):
        return f"模拟笔记：{step['description']}", step.get("queries", [])

    monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
    monkeypatch.setattr("deep_research.nodes.supervisor.run_single_step", fake_run)

    graph = build_graph(Config(max_parallel_workers=2), reflect=False, supervisor=True)
    final = graph.invoke(
        {"task": "测试任务"},
        config={"configurable": {"thread_id": "e2e-supervisor"}},
    )

    assert final["status"] == "complete"
    assert final["final_report"].startswith("这是一份端到端测试")
    assert len(final["completed_steps"]) == 2  # 两个步骤一批并行完成
    assert fake.calls == 2  # planner + writer（worker 走 mock 的 run_single_step）


def test_checkpoint_resume_skips_completed_work(monkeypatch):
    """断点续跑：writer 前中断，同一 thread_id 恢复后不重跑 planner/executor。

    验证方式：模型调用次数——中断后恢复只多 writer 一次（已完成步骤未重跑）。
    若 Checkpoint 失效会从头执行（planner 再调一次），calls 会变成 3。
    """
    fake = FakeModel([PLAN_JSON, REPORT])  # 仅允许 planner + writer 各调一次
    monkeypatch.setattr("deep_research.model.build_model", lambda *a, **k: fake)
    monkeypatch.setattr("deep_research.graph.executor_node", _fake_executor_factory)

    graph = build_graph(Config(), reflect=False)
    config = {"configurable": {"thread_id": "ckpt-resume-test"}}

    # 第一次：中断在 writer 前（planner + executor 已完成，writer 未跑）
    state = graph.invoke({"task": "测试任务"}, config=config, interrupt_before=["writer"])
    assert fake.calls == 1  # 只调了 planner
    assert len(state.get("completed_steps", [])) == 2  # executor 已完成两步

    # 恢复：从断点继续，只跑 writer
    final = graph.invoke(None, config=config)
    assert fake.calls == 2  # 只多 writer 一次 → 已完成步骤未重跑
    assert final["status"] == "complete"
    assert final["final_report"].startswith("这是一份端到端测试")
