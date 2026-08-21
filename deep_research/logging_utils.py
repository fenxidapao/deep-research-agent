"""统一日志配置：入口脚本调用 setup_logging() 一次，包内各模块用 get_logger()。

格式：时间 | 级别 | 模块名 | 消息
CLI 场景 basicConfig 到 stderr，保证 --json 模式 stdout 纯净（只含 JSON）。
"""

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"


def setup_logging(level: int = logging.INFO, stream=None) -> None:
    logging.basicConfig(
        level=level,
        format=_FORMAT,
        datefmt=_DATE_FORMAT,
        stream=stream or sys.stderr,
        force=True,  # 覆盖可能存在的第三方配置（如 uvicorn 外的其他入口）
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
