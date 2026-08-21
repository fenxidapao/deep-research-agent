"""模型工厂：统一创建 smolagents 模型实例。

主用 DeepSeek API（OpenAI 兼容接口），Ollama 作为离线降级。
smolagents>=1.26 使用 OpenAIModel（OpenAI 兼容 API 客户端）。

支持 Token 用量统计：UsageCounter 包装模型，累计每次调用的 input/output tokens。
Supervisor 并行模式下多个 worker 共享计数，内部加锁保证线程安全。
"""

import threading
from typing import Any, Optional

from smolagents import OpenAIModel

from .config import Config
from .logging_utils import get_logger

logger = get_logger("model")


class UsageCounter:
    """累计模型调用产生的 token 用量（图内所有节点共享一个实例，线程安全）。"""

    def __init__(self):
        self._lock = threading.RLock()
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self.input_tokens += input_tokens or 0
            self.output_tokens += output_tokens or 0


class _CountingModel:
    """包装真实模型：统计每次调用的 token 用量，其余行为透传。

    smolagents 的 Agent 内部调用 model.generate()（非 __call__），
    因此两个入口都要包装，否则 CodeAgent 路径会漏统计。
    """

    def __init__(self, inner, counter: UsageCounter):
        self._inner = inner
        self._counter = counter

    def __call__(self, messages, **kwargs) -> Any:
        return self._count(self._inner(messages, **kwargs))

    def generate(self, messages, **kwargs) -> Any:
        return self._count(self._inner.generate(messages, **kwargs))

    def _count(self, resp) -> Any:
        usage = getattr(resp, "token_usage", None)
        if usage is not None:
            self._counter.add(usage.input_tokens, usage.output_tokens)
        return resp

    def __getattr__(self, name: str):
        # 透传内部模型的其他属性（model_id 等），避免破坏 smolagents 内部逻辑
        return getattr(self._inner, name)


def build_model(cfg: Config, counter: Optional[UsageCounter] = None):
    """按配置创建模型。provider=deepseek 用 API，provider=ollama 用本地。

    counter 非空时返回包装后的计数模型。
    """
    if cfg.provider == "ollama":
        # Ollama 暴露 OpenAI 兼容接口 /v1
        model = OpenAIModel(
            model_id=cfg.ollama_model,
            api_base=cfg.ollama_base_url + "/v1",
            api_key="ollama",  # 本地服务不校验
            temperature=0.3,
            max_tokens=2048,
        )
    else:
        model = OpenAIModel(
            model_id=cfg.deepseek_model,
            api_base=cfg.deepseek_base_url,
            api_key=cfg.deepseek_api_key,
            temperature=0.3,
            max_tokens=2048,
        )
    if counter is not None:
        logger.info("模型已启用 token 计数: provider=%s model=%s", cfg.provider, model.model_id)
        return _CountingModel(model, counter)
    return model
