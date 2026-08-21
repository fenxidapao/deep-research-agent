"""运行配置：模型、搜索、预算。全部支持环境变量 / .env 覆盖。"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


@dataclass
class Config:
    # ---- 模型 ----
    provider: str = field(default_factory=lambda: _env("MODEL_PROVIDER", "deepseek"))
    deepseek_api_key: str = field(default_factory=lambda: _env("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
    deepseek_model: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-chat"))
    ollama_base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:7b"))

    # ---- 搜索 ----
    search_provider: str = field(default_factory=lambda: _env("SEARCH_PROVIDER", "bing"))
    tavily_api_key: str = field(default_factory=lambda: _env("TAVILY_API_KEY", ""))

    # ---- 预算 ----
    max_plan_steps: int = field(default_factory=lambda: int(_env("MAX_PLAN_STEPS", "6")))
    max_iterations: int = field(default_factory=lambda: int(_env("MAX_ITERATIONS", "4")))
    max_searches_per_step: int = field(default_factory=lambda: int(_env("MAX_SEARCHES_PER_STEP", "5")))
    max_report_length: int = field(default_factory=lambda: int(_env("MAX_REPORT_LENGTH", "3000")))

    # ---- 断点续跑 ----
    checkpoint_dir: str = field(default_factory=lambda: _env("CHECKPOINT_DIR", "./.checkpoints"))

    # ---- 经验沉淀 ----
    memory_file: str = field(default_factory=lambda: _env("MEMORY_FILE", "memory/experiences.json"))

    # ---- 并行研究（supervisor 模式） ----
    max_parallel_workers: int = field(default_factory=lambda: int(_env("MAX_PARALLEL_WORKERS", "3")))


def get_config() -> Config:
    cfg = Config()
    if cfg.provider == "deepseek" and not cfg.deepseek_api_key:
        raise ValueError(
            "缺少 DEEPSEEK_API_KEY：请在 .env 中配置（可复制 .env.example 重命名）。"
            "DeepSeek 平台：https://platform.deepseek.com"
        )
    if cfg.search_provider == "tavily" and not cfg.tavily_api_key:
        raise ValueError("SEARCH_PROVIDER=tavily 但缺少 TAVILY_API_KEY，或改用 bing（国内直连免费，无需 key）。")
    return cfg
