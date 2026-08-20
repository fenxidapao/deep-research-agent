"""模型工厂：统一创建 smolagents 模型实例。

主用 DeepSeek API（OpenAI 兼容接口），Ollama 作为离线降级。
smolagents>=1.26 使用 OpenAIModel（OpenAI 兼容 API 客户端）。
"""

from smolagents import OpenAIModel

from .config import Config


def build_model(cfg: Config) -> OpenAIModel:
    """按配置创建模型。provider=deepseek 用 API，provider=ollama 用本地。"""
    if cfg.provider == "ollama":
        # Ollama 暴露 OpenAI 兼容接口 /v1
        return OpenAIModel(
            model_id=cfg.ollama_model,
            api_base=cfg.ollama_base_url + "/v1",
            api_key="ollama",  # 本地服务不校验
            temperature=0.3,
            max_tokens=2048,
        )
    return OpenAIModel(
        model_id=cfg.deepseek_model,
        api_base=cfg.deepseek_base_url,
        api_key=cfg.deepseek_api_key,
        temperature=0.3,
        max_tokens=2048,
    )
