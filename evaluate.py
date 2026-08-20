"""量化评测脚本：跑评测集，输出关键指标到 eval_set/metrics.json。

指标：
- 规划成功率：Planner 产出 1~max_plan_steps 个可用步骤的比例
- 报告完成率：成功生成 final_report 的比例
- 答案准确率（自动）：must_contain 关键词命中率
- 效率：平均执行步骤数 / 平均循环轮数 / 平均耗时
- 断点恢复耗时：重跑同一 thread_id 到指定 checkpoint 的耗时（对比全量）

用法：python evaluate.py [--limit N] [--resume-test]
"""

import argparse
import json
import sys
import time

from deep_research import build_graph, get_config


def load_tasks(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["tasks"]


def run_single(graph, task: dict) -> dict:
    t0 = time.time()
    final = graph.invoke(
        {"task": task["task"]},
        config={"configurable": {"thread_id": f"eval-{task['id']}"}},
    )
    elapsed = round(time.time() - t0, 1)

    report = final.get("final_report", "")
    must = task.get("must_contain", [])
    hits = [k for k in must if k in report]

    return {
        "id": task["id"],
        "category": task.get("category", ""),
        "plan_steps": len(final.get("plan", [])),
        "executed_steps": len(final.get("completed_steps", [])),
        "iterations": final.get("iteration", 0),
        "status": final.get("status", ""),
        "elapsed": elapsed,
        "report_len": len(report),
        "hit_ratio": round(len(hits) / len(must), 2) if must else 0.0,
        "hits": hits,
    }


def summarize(results: list[dict], max_plan_steps: int = 6) -> dict:
    n = len(results)
    plan_ok = sum(1 for r in results if 1 <= r["plan_steps"] <= max_plan_steps)
    completed = sum(1 for r in results if r["report_len"] > 100)
    avg_hit = sum(r["hit_ratio"] for r in results) / n if n else 0

    return {
        "tasks": n,
        "规划成功率": round(plan_ok / n, 2) if n else 0,
        "报告完成率": round(completed / n, 2) if n else 0,
        "答案命中率(avg)": round(avg_hit, 2),
        "平均执行步骤": round(sum(r["executed_steps"] for r in results) / n, 1) if n else 0,
        "平均循环轮数": round(sum(r["iterations"] for r in results) / n, 1) if n else 0,
        "平均耗时(s)": round(sum(r["elapsed"] for r in results) / n, 1) if n else 0,
        "总耗时(s)": round(sum(r["elapsed"] for r in results), 1),
    }


def resume_test(graph, thread_id: str = "eval-resume") -> float:
    """断点恢复耗时测试：向一个 thread_id 发两次任务，第二次复用 checkpoint。"""
    t0 = time.time()
    graph.invoke({"task": "测试断点恢复"}, config={"configurable": {"thread_id": thread_id}})
    graph.invoke({"task": "测试断点恢复"}, config={"configurable": {"thread_id": thread_id}})
    return round(time.time() - t0, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    parser.add_argument("--tasks", default="eval_set/tasks.json")
    parser.add_argument("--resume-test", action="store_true", help="附加断点恢复耗时测试")
    args = parser.parse_args()

    cfg = get_config()
    graph = build_graph(cfg)
    tasks = load_tasks(args.tasks)
    if args.limit:
        tasks = tasks[: args.limit]

    print(f"评测集: {len(tasks)} 条 | provider={cfg.provider} search={cfg.search_provider}\n")
    results = []
    for i, t in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] #{t['id']} [{t.get('category','')}] {t['task'][:40]}...")
        r = run_single(graph, t)
        results.append(r)
        print(f"    -> 步骤 {r['executed_steps']}/{r['plan_steps']} | 轮数 {r['iterations']} | "
              f"命中 {r['hit_ratio']} | 耗时 {r['elapsed']}s | {r['status']}\n")

    metrics = summarize(results, max_plan_steps=cfg.max_plan_steps)
    if args.resume_test:
        metrics["断点恢复测试耗时(s)"] = resume_test(graph)

    out = {"metrics": metrics, "detail": results}
    with open("eval_set/metrics.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("=" * 50)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print("=" * 50)
    print("详细结果已写入 eval_set/metrics.json")


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)
