"""CLI 入口：python main.py "调研问题" [--model deepseek|ollama] [--search bing|tavily] [--json]"""

import argparse
import json
import os
import sys
import time

from deep_research import build_graph, get_config
from deep_research.logging_utils import get_logger, setup_logging

logger = get_logger("cli")


def run(task: str, verbose: bool = True) -> dict:
    cfg = get_config()
    graph = build_graph(cfg)
    thread_id = f"run-{int(time.time())}"

    t0 = time.time()
    final = graph.invoke(
        {"task": task},
        config={"configurable": {"thread_id": thread_id}},
    )
    elapsed = time.time() - t0
    logger.info("任务完成: thread=%s 状态=%s 耗时=%.1fs", thread_id, final.get("status"), elapsed)

    if verbose:
        print("=" * 60)
        print(f"调研简报: {final.get('research_brief', '')[:200]}")
        print(f"计划步骤: {len(final.get('plan', []))} 步")
        print(f"实际执行: {len(final.get('completed_steps', []))} 步 | 循环 {final.get('iteration', 0)} 轮")
        print(f"状态: {final.get('status')} | 耗时 {elapsed:.1f}s")
        print("=" * 60)
        for note in final.get("intermediate_results", []):
            print(note[:400])
            print("-" * 60)
        print("\n===== 最终报告 =====\n")
        print(final.get("final_report", "（未生成）"))
    return {"final": final, "elapsed": elapsed}


def main():
    setup_logging()  # 日志走 stderr，--json 模式 stdout 只含 JSON
    parser = argparse.ArgumentParser(description="Deep Research Agent（LangGraph + smolagents）")
    parser.add_argument("task", help="调研问题")
    parser.add_argument("--model", choices=["deepseek", "ollama"], default=None, help="模型 provider（默认读 .env）")
    parser.add_argument("--search", choices=["bing", "tavily"], default=None, help="搜索 provider（默认读 .env）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供脚本/评测使用）")
    args = parser.parse_args()

    if args.model:
        os.environ["MODEL_PROVIDER"] = args.model
    if args.search:
        os.environ["SEARCH_PROVIDER"] = args.search

    try:
        result = run(args.task)
    except ValueError as e:
        logger.error("配置错误: %s", e)
        sys.exit(1)

    if args.json:
        print(json.dumps({"task": args.task, "elapsed": result["elapsed"], **result["final"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
