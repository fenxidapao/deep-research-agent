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

        report = model([{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}]).content
        return {"final_report": str(report), "status": "complete"}

    return node
