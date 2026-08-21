"""Writer 节点：Reflector 判定 complete 后，汇总研究笔记生成最终报告。"""

from typing import Any

from ..config import Config
from ..logging_utils import get_logger
from ..prompts import TODAY, WRITER_SYSTEM_PROMPT
from ..state import ResearchState

logger = get_logger("writer")


def writer_node(cfg: Config, counter=None):
    """返回 Writer 节点函数（闭包注入配置）。"""

    def node(state: ResearchState) -> dict[str, Any]:
        from ..model import build_model

        model = build_model(cfg, counter)
        notes = "\n\n".join(state.get("intermediate_results", []))
        if not notes.strip():
            notes = "（未收集到研究笔记）"

        prompt = WRITER_SYSTEM_PROMPT.format(today=TODAY, max_length=cfg.max_report_length)
        user_msg = (
            f"调研简报：{state.get('research_brief', state['task'])}\n\n"
            f"用户原始任务：{state['task']}\n\n"
            f"研究笔记：\n{notes}"
        )

        # DeepSeek 偶发返回空 content：空/过短输出重试，最多 3 次
        report = ""
        for attempt in range(3):
            raw = model([{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}]).content
            report = str(raw or "").strip()
            if len(report) >= 50:
                break
            logger.warning("Writer 第 %d 次输出过短(%d 字)，重试", attempt + 1, len(report))
        if len(report) < 50:
            # 兜底：输出研究笔记原文（轻量 Markdown 化），保证报告不为空
            logger.error("Writer 三次重试仍失败，使用研究笔记原文兜底")
            notes_body = notes[: cfg.max_report_length]
            report = f"（自动报告生成失败，以下为研究笔记原文整理）\n\n# 研究笔记汇总\n\n{notes_body}"
        return {"final_report": report, "status": "complete"}

    return node
