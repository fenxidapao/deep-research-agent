"""Graph 层测试：Reflector 之后的条件路由 _route 三路由。"""

from deep_research.graph import _route


def test_complete_routes_to_writer():
    assert _route({"status": "complete"}) == "writer"


def test_replan_routes_to_planner():
    assert _route({"status": "replan"}) == "planner"


def test_running_routes_to_executor():
    assert _route({"status": "running"}) == "executor"


def test_unknown_status_defaults_to_executor():
    assert _route({"status": "weird"}) == "executor"


def test_missing_status_defaults_to_executor():
    assert _route({}) == "executor"
