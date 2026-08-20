"""Writer 节点：Reflector 判定 complete 后，汇总研究笔记生成最终报告。"""

from typing import Any

from ..config import Config
from ..prompts import TODAY, WRITER_SYSTEM_PROMPT
from ..state import ResearchState


def writer_node(cfg: Config):
    """返回 Writer 节点函数（闭包注入配置）。"""

    def node(state: ResearchState) -> dict[str, Any]:
        from ..model import build_model

        model = build_model(cfg)
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
        if len(report) < 50:
            # 兜底：直接输出研究笔记原文，保证报告不为空
            report = f"（自动报告生成失败，以下为研究笔记原文）\n\n{notes[: cfg.max_report_length]}"
        return {"final_report": report, "status": "complete"}

    return node
