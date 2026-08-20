"""LangGraph 状态定义：任务、计划、中间结果、反思、最终报告。"""

import operator
from typing import Annotated, TypedDict


def _append(current: list[str], new: list[str]) -> list[str]:
    """列表累加 reducer：节点返回的新元素追加到已有列表。"""
    return current + new


class PlanStep(TypedDict):
    """单步研究计划。"""

    id: int            # 步骤序号（1 起）
    description: str   # 该步要调研什么
    queries: list[str] # 建议搜索关键词


class ResearchState(TypedDict, total=False):
    # ---- 输入 ----
    task: str                              # 用户原始任务

    # ---- 规划 ----
    research_brief: str                    # Planner 细化后的调研主题（含约束）
    plan: list[PlanStep]                   # 步骤列表

    # ---- 执行进度 ----
    current_step: int                      # 当前步骤索引（0 起）
    completed_steps: Annotated[list[str], _append]      # 已完成步骤描述
    intermediate_results: Annotated[list[str], _append] # 每步研究笔记
    search_history: Annotated[list[str], _append]       # 已搜过的关键词（防重复）

    # ---- 反思 ----
    reflection: str                        # 最近一次反思结论
    iteration: int                         # 循环轮数
    status: str                            # running | replan | complete

    # ---- 输出 ----
    final_report: str                      # 最终研究报告
