"""反思前后对照实验（独立脚本，逐条运行）。

用法：
  python ablation.py --id 1            # 跑单条任务的有反思/无反思对比
  python ablation.py --id 1 --id 3     # 跑多条（各自独立进程，互不影响）
  python ablation.py --all             # 跑全部评测集

结果追加写入 eval_set/ablation.jsonl（逐条落盘，中断不丢）。
"""

import argparse
import json
import os
import sys
import time

from deep_research import build_graph, get_config
from evaluate import run_single

ABLATION_FILE = "eval_set/ablation.jsonl"


def load_tasks(path: str = "eval_set/tasks.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["tasks"]


def append_row(row: dict) -> None:
    os.makedirs(os.path.dirname(ABLATION_FILE), exist_ok=True)
    with open(ABLATION_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_one(task: dict, cfg) -> dict:
    """对单条任务跑 有反思/无反思 两版，返回对比行。"""
    g_on = build_graph(cfg, reflect=True)
    g_off = build_graph(cfg, reflect=False)

    print(f"  有反思版运行中...")
    r_on = run_single(g_on, task)
    print(f"  无反思版运行中...")
    r_off = run_single(g_off, task)

    row = {
        "id": task["id"],
        "category": task.get("category", ""),
        "task": task["task"][:40],
        "有反思命中": r_on["hit_ratio"],
        "无反思命中": r_off["hit_ratio"],
        "有反思步骤/轮数": f"{r_on['executed_steps']}/{r_on['iterations']}",
        "无反思步骤/轮数": f"{r_off['executed_steps']}/{r_off['iterations']}",
        "有反思耗时(s)": r_on["elapsed"],
        "无反思耗时(s)": r_off["elapsed"],
        "有反思tokens": g_on.usage_counter.total_tokens,
        "无反思tokens": g_off.usage_counter.total_tokens,
    }
    append_row(row)
    print(f"  -> #{task['id']} 有反思命中{r_on['hit_ratio']} vs 无反思命中{r_off['hit_ratio']} | "
          f"tokens {row['有反思tokens']} vs {row['无反思tokens']} | 耗时 {r_on['elapsed']}s vs {r_off['elapsed']}s")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, action="append", default=[], help="任务 id（可多次指定）")
    parser.add_argument("--all", action="store_true", help="跑全部评测集")
    args = parser.parse_args()

    cfg = get_config()
    tasks = load_tasks()
    by_id = {t["id"]: t for t in tasks}

    if args.all:
        targets = tasks
    else:
        targets = [by_id[i] for i in args.id if i in by_id]
    if not targets:
        print("未指定有效任务 id，用 --id 或 --all", file=sys.stderr)
        sys.exit(1)

    print(f"反思前后对照实验：{len(targets)} 条 | provider={cfg.provider} search={cfg.search_provider}\n")
    for t in targets:
        print(f"#{t['id']} [{t.get('category','')}] {t['task'][:40]}...")
        try:
            run_one(t, cfg)
        except Exception as e:  # noqa: BLE001
            print(f"  !!! #{t['id']} 运行失败: {type(e).__name__}: {e}（已跳过，可单独重跑）")
        print()

    # 汇总
    rows = []
    if os.path.exists(ABLATION_FILE):
        with open(ABLATION_FILE, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    if rows:
        n = len(rows)
        on = sum(r["有反思命中"] for r in rows) / n
        off = sum(r["无反思命中"] for r in rows) / n
        print("=" * 50)
        print(f"汇总（{n} 条）：有反思命中率 {on:.2f} vs 无反思命中率 {off:.2f}，提升 {on - off:+.2f}")
        print("详细数据: eval_set/ablation.jsonl")


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)
