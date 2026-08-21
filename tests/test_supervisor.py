"""Supervisor 节点测试：并行分发、批量推进、失败容错、状态累加。

通过 mock `deep_research.nodes.supervisor.run_single_step`（supervisor.py 模块级名字），
不实例化 CodeAgent，秒级验证分发逻辑。
"""

from deep_research.config import Config
from deep_research.nodes.supervisor import supervisor_node


def _plan(n: int) -> list[dict]:
    return [{"id": i + 1, "description": f"步骤{i+1}", "queries": [f"q{i+1}"]} for i in range(n)]


def _cfg(tmp_path, workers: int = 3) -> Config:
    return Config(memory_file=str(tmp_path / "m.json"), max_parallel_workers=workers)


class TestSupervisorNode:
    def test_batches_parallel_steps(self, monkeypatch, tmp_path):
        """plan 5 步、max_parallel=3：第一次取 3 步，第二次取 2 步；调用顺序保持。"""
        called_ids = []

        def fake_run(cfg, counter, brief, task, step, history, memory=None):
            called_ids.append(step["id"])
            return f"笔记{step['id']}", step.get("queries", [])

        monkeypatch.setattr("deep_research.nodes.supervisor.run_single_step", fake_run)
        node = supervisor_node(_cfg(tmp_path, workers=3))

        state = {"task": "t", "research_brief": "b", "plan": _plan(5), "current_step": 0}
        out1 = node(dict(state))
        assert out1["current_step"] == 3
        assert len(out1["completed_steps"]) == 3
        assert len(out1["intermediate_results"]) == 3

        out2 = node({**state, "current_step": out1["current_step"]})
        assert out2["current_step"] == 5
        assert len(out2["completed_steps"]) == 2
        assert sorted(called_ids) == [1, 2, 3, 4, 5]  # 5 步全部执行（执行顺序由线程调度决定）

    def test_all_steps_done_returns_complete(self, tmp_path):
        node = supervisor_node(_cfg(tmp_path))
        out = node({"task": "t", "plan": [{"id": 1, "description": "d", "queries": []}], "current_step": 1})
        assert out == {"status": "complete"}

    def test_worker_failure_isolated(self, monkeypatch, tmp_path):
        """单 worker 失败返回错误笔记，不影响其他 worker 的结果。"""

        def fake_run(cfg, counter, brief, task, step, history, memory=None):
            if step["id"] == 2:
                return "（步骤2 执行失败：ValueError: boom）", []
            return f"笔记{step['id']}", []

        monkeypatch.setattr("deep_research.nodes.supervisor.run_single_step", fake_run)
        node = supervisor_node(_cfg(tmp_path, workers=3))
        out = node({"task": "t", "research_brief": "b", "plan": _plan(3), "current_step": 0})

        assert out["current_step"] == 3
        assert len(out["intermediate_results"]) == 3
        assert "笔记1" in out["intermediate_results"][0]
        assert "执行失败" in out["intermediate_results"][1]
        assert "笔记3" in out["intermediate_results"][2]

    def test_search_history_accumulates(self, monkeypatch, tmp_path):
        def fake_run(cfg, counter, brief, task, step, history, memory=None):
            return "note", [f"q{step['id']}"]

        monkeypatch.setattr("deep_research.nodes.supervisor.run_single_step", fake_run)
        node = supervisor_node(_cfg(tmp_path, workers=3))
        out = node({"task": "t", "research_brief": "b", "plan": _plan(2), "current_step": 0})
        assert out["search_history"] == ["q1", "q2"]

    def test_worker_exception_survives(self, monkeypatch, tmp_path):
        """run_single_step 意外抛异常时，supervisor 兜底为失败笔记，整批不崩。"""

        def fake_run(*args, **kwargs):
            raise RuntimeError("意外异常")

        monkeypatch.setattr("deep_research.nodes.supervisor.run_single_step", fake_run)
        node = supervisor_node(_cfg(tmp_path, workers=3))
        out = node({"task": "t", "research_brief": "b", "plan": _plan(2), "current_step": 0})
        assert out["current_step"] == 2
        assert all("执行异常" in n for n in out["intermediate_results"])

    def test_run_single_step_records_failure(self, monkeypatch, tmp_path):
        """真实 run_single_step 中模型构建失败 → 失败笔记 + 经验沉淀（闭环写入端）。"""
        from deep_research.memory import ExperienceMemory
        from deep_research.nodes.executor import run_single_step

        def boom(*a, **k):
            raise RuntimeError("搜索超时")

        monkeypatch.setattr("deep_research.model.build_model", boom)
        mem = ExperienceMemory(str(tmp_path / "m.json"))
        note, fresh = run_single_step(
            Config(), None, "简报", "测试任务",
            {"id": 1, "description": "d", "queries": []}, [], mem,
        )
        assert "执行失败" in note
        assert fresh == []
        assert len(mem) == 1  # 经验已落盘
        assert "搜索超时" in mem.relevant("测试任务")[0]["lesson"]
