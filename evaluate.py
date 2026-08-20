"""量化评测脚本：跑评测集，输出关键指标到 eval_set/metrics.json。

指标：
- 规划成功率：Planner 产出 1~max_plan_steps 个可用步骤的比例
- 报告完成率：成功生成 final_report 的比例
- 答案准确率（自动）：must_contain 关键词命中率
- 效率：平均执行步骤数 / 平均循环轮数 / 平均耗时
- 断点恢复耗时：重跑同一 thread_id 到指定 checkpoint 的耗时（对比全量）

用法：python evaluate.py [--limit N] [--resume-test] [--fresh]
断点续跑：每条结果实时写入 eval_set/progress.jsonl，中断后重跑自动跳过已完成任务；
         加 --fresh 可清空进度重跑。
"""

import argparse
import json
import os
import sys
import time

from deep_research import build_graph, get_config

PROGRESS_FILE = "eval_set/progress.jsonl"


def load_progress() -> dict[int, dict]:
    """读取已完成的任务结果（id -> result）。"""
    done: dict[int, dict] = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done[int(r["id"])] = r
    return done


def append_progress(r: dict) -> None:
    """立即把一条结果追加到进度文件（原子单行写）。"""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")


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
    parser.add_argument("--fresh", action="store_true", help="清空进度文件重跑全部")
    args = parser.parse_args()

    if args.fresh and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("已清空进度文件\n")

    cfg = get_config()
    graph = build_graph(cfg)
    tasks = load_tasks(args.tasks)
    if args.limit:
        tasks = tasks[: args.limit]

    done = load_progress()
    pending = [t for t in tasks if t["id"] not in done]
    print(f"评测集: {len(tasks)} 条 | provider={cfg.provider} search={cfg.search_provider} | "
          f"已完成 {len(done)} 条，本次将跑 {len(pending)} 条\n")

    results = list(done.values())  # 历史结果直接复用
    for i, t in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}] #{t['id']} [{t.get('category','')}] {t['task'][:40]}...")
        r = run_single(graph, t)
        results.append(r)
        append_progress(r)  # 立即落盘，中断不丢
        print(f"    -> 步骤 {r['executed_steps']}/{r['plan_steps']} | 轮数 {r['iterations']} | "
              f"命中 {r['hit_ratio']} | 耗时 {r['elapsed']}s | {r['status']}\n")

    results.sort(key=lambda r: r["id"])
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
