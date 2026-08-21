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
    # 大小写不敏感匹配（报告里可能写 LangGraph/CrewAI 而非 langgraph/crewAI）
    report_lower = report.lower()
    hits = [k for k in must if k.lower() in report_lower]

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


def resume_test(graph, task: str, thread_id: str = "eval-resume") -> dict:
    """断点恢复耗时测试：在 writer 节点前中断，再用同一 thread_id 续跑。

    返回：{中断前耗时, 恢复后耗时, 恢复占比}
    恢复占比越小，说明 Checkpoint 续跑价值越高（不用重跑已完成的研究步骤）。
    """
    t0 = time.time()
    graph.invoke(
        {"task": task},
        config={"configurable": {"thread_id": thread_id}},
        interrupt_before=["writer"],  # 注意：关键字参数，不是 config 键
    )
    t_before = round(time.time() - t0, 1)

    t1 = time.time()
    graph.invoke(None, config={"configurable": {"thread_id": thread_id}})  # 从断点继续
    t_after = round(time.time() - t1, 1)

    return {
        "中断前耗时(s)": t_before,
        "恢复后耗时(s)": t_after,
        "恢复耗时占比": round(t_after / max(t_before + t_after, 0.1), 2),
    }


def ablation(tasks: list[dict], cfg, limit: int = 5) -> list[dict]:
    """反思前后对照实验：同一批任务分别用 有反思/无反思 跑，对比命中率与成本。

    无反思版（reflect=False）：顺序执行所有计划步骤后直接写报告，Reflector 不做语义判定。
    """
    from deep_research import build_graph as build

    rows = []
    for t in tasks[:limit]:
        g_on = build(cfg, reflect=True)
        g_off = build(cfg, reflect=False)
        r_on = run_single(g_on, t)
        r_off = run_single(g_off, t)
        rows.append(
            {
                "id": t["id"],
                "task": t["task"][:30],
                "有反思命中": r_on["hit_ratio"],
                "无反思命中": r_off["hit_ratio"],
                "有反思步骤/轮数": f"{r_on['executed_steps']}/{r_on['iterations']}",
                "无反思步骤/轮数": f"{r_off['executed_steps']}/{r_off['iterations']}",
                "有反思tokens": g_on.usage_counter.total_tokens,
                "无反思tokens": g_off.usage_counter.total_tokens,
            }
        )
        print(f"    #{t['id']} 有反思命中{r_on['hit_ratio']} vs 无反思命中{r_off['hit_ratio']} | "
              f"tokens {g_on.usage_counter.total_tokens} vs {g_off.usage_counter.total_tokens}")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    parser.add_argument("--tasks", default="eval_set/tasks.json")
    parser.add_argument("--resume-test", action="store_true", help="附加断点恢复耗时测试")
    parser.add_argument("--ablation", type=int, default=0, metavar="N", help="反思前后对照实验，跑前 N 条")
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

    extra = {}
    if args.resume_test:
        # 选评测集里最快的任务（#15 全球人口，全量约 2 分钟）做中断恢复测试，省时省钱
        quick = next((t for t in tasks if t["id"] == 15), tasks[0])
        rt = resume_test(graph, quick["task"])
        metrics["断点恢复"] = rt
        extra["resume_test"] = rt
    # token 统计放最后：resume_test 也会消耗 token，需在之后取值
    metrics["总token消耗"] = graph.usage_counter.total_tokens
    if args.ablation:
        print(f"\n=== 反思前后对照实验（{args.ablation} 条）===")
        rows = ablation(tasks, cfg, limit=args.ablation)
        on_hit = sum(r["有反思命中"] for r in rows) / len(rows)
        off_hit = sum(r["无反思命中"] for r in rows) / len(rows)
        metrics["反思前后命中率对比"] = {"有反思": round(on_hit, 2), "无反思": round(off_hit, 2),
                                    "提升": round(on_hit - off_hit, 2)}
        extra["ablation"] = rows

    out = {"metrics": metrics, "detail": results, **extra}
    try:
        # 原子写：先写 .tmp 再替换，避免直接覆盖目标被占用/沙箱拦截时崩溃（8/21 实测踩坑）
        tmp = "eval_set/metrics.json.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        os.replace(tmp, "eval_set/metrics.json")
    except OSError as e:
        print(f"警告: metrics.json 写入失败（{e}）；评测数据已保留在 progress.jsonl，可手工恢复", file=sys.stderr)

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
