"""对比评测：纯 web 搜索 vs web + CourseRAG（课程知识库）。

验证集成价值：同样 3 条课程题，两种配置各跑一遍，对比命中率/耗时/成本。

用法：
  python eval_rag_compare.py [--limit N] [--rag-url http://127.0.0.1:8000]
说明：
  - RAG 服务需先启动（CourseRAG: uvicorn main:app --port 8000/8001），否则 RAG 模式自动降级为 web；
  - 结果实时落盘 eval_set/rag_compare.jsonl（断点续跑，中断后重跑自动跳过已完成）；
  - 两种模式用不同 thread_id（防 LangGraph checkpoint 互相污染）。
"""

import argparse
import json
import os
import sys
import time
from dataclasses import replace

from deep_research import build_graph, get_config
from deep_research.tools import get_tool_stats, reset_tool_stats

PROGRESS_FILE = "eval_set/rag_compare.jsonl"


def load_tasks(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["tasks"]


def load_progress() -> set[tuple[int, str]]:
    done = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done.add((int(r["id"]), r["mode"]))
    return done


def append_progress(r: dict) -> None:
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_one(cfg, task: dict, mode: str) -> dict:
    """跑单条任务（mode: web | web+rag），返回结果。"""
    reset_tool_stats()
    graph = build_graph(cfg)
    t0 = time.time()
    final = graph.invoke(
        {"task": task["task"]},
        config={"configurable": {"thread_id": f"ragcmp-{task['id']}-{mode}"}},
    )
    elapsed = round(time.time() - t0, 1)

    report = final.get("final_report", "")
    report_lower = report.lower()
    must = task.get("must_contain", [])
    hits = [k for k in must if k.lower() in report_lower]

    stats = get_tool_stats()
    rag_calls = stats.get("course_retrieve", {}).get("calls", 0)

    return {
        "id": task["id"],
        "mode": mode,
        "task": task["task"],
        "hit_ratio": round(len(hits) / len(must), 2) if must else 0.0,
        "hits": hits,
        "executed_steps": len(final.get("completed_steps", [])),
        "iterations": final.get("iteration", 0),
        "elapsed": elapsed,
        "tokens": graph.usage_counter.total_tokens,
        "course_retrieve_calls": rag_calls,
        "status": final.get("status", ""),
        "report_len": len(report),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tasks", default="eval_set/rag_tasks.json")
    parser.add_argument("--rag-url", default=None, help="RAG 服务地址，默认读 .env RAG_BASE_URL")
    args = parser.parse_args()

    base_cfg = get_config()
    rag_url = args.rag_url or base_cfg.rag_base_url

    # 两种配置：纯 web（不挂 course_retrieve） vs web+RAG（用 replace 生成独立副本，避免共享引用）
    cfg_web = replace(base_cfg, rag_base_url="")
    cfg_rag = replace(base_cfg, rag_base_url=rag_url)

    tasks = load_tasks(args.tasks)
    if args.limit:
        tasks = tasks[: args.limit]

    done = load_progress()
    rows = []
    for t in tasks:
        for mode, cfg in (("web", cfg_web), ("web+rag", cfg_rag)):
            key = (t["id"], mode)
            if key in done:
                continue
            print(f"[{t['id']}] {mode} | {t['task'][:40]}...", flush=True)
            r = run_one(cfg, t, mode)
            rows.append(r)
            append_progress(r)
            print(f"    -> 命中 {r['hit_ratio']} {r['hits']} | 步骤 {r['executed_steps']} | "
                  f"轮数 {r['iterations']} | 耗时 {r['elapsed']}s | tokens {r['tokens']} | "
                  f"course_retrieve调用 {r['course_retrieve_calls']}\n", flush=True)

    # 汇总（含历史结果）
    all_rows = []
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_rows.append(json.loads(line))
    for r in rows:
        all_rows.append(r)

    by_mode = {}
    for r in all_rows:
        by_mode.setdefault(r["mode"], []).append(r)

    print("=" * 60)
    for mode, rs in by_mode.items():
        n = len(rs)
        avg_hit = sum(r["hit_ratio"] for r in rs) / n
        avg_time = sum(r["elapsed"] for r in rs) / n
        total_tokens = sum(r["tokens"] for r in rs)
        rag_calls = sum(r["course_retrieve_calls"] for r in rs)
        print(f"[{mode}] {n} 条 | 平均命中 {round(avg_hit, 2)} | 平均耗时 {round(avg_time, 1)}s "
              f"| 总tokens {total_tokens} | course_retrieve调用 {rag_calls}")

    # 配对对比（web vs web+rag 同 id）
    if "web" in by_mode and "web+rag" in by_mode:
        web = {r["id"]: r for r in by_mode["web"]}
        rag = {r["id"]: r for r in by_mode["web+rag"]}
        diffs = []
        for tid in web:
            if tid in rag:
                diffs.append(rag[tid]["hit_ratio"] - web[tid]["hit_ratio"])
        if diffs:
            avg_diff = round(sum(diffs) / len(diffs), 2)
            print(f"\n配对对比（web+rag - web 命中率）：{diffs} → 平均 {avg_diff:+.2f}")
            print("结论：正数说明课程知识库提升了课程题命中率")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)
