"""搜索与抓取工具（smolagents Tool 格式）。

- web_search: bing（默认，国内直连免费，自研 HTML 解析）/ tavily（需 key，质量更高）
- fetch_page: 抓取网页正文转纯文本，供 CodeAgent 深度阅读

注：DuckDuckGo 国内不可达，已弃用。
"""

import html
import re
from typing import Optional

import requests
from lxml import html as lh
from smolagents import Tool

_BING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _clean_html(raw: str, max_chars: int = 6000) -> str:
    """粗糙但够用的 HTML→纯文本转换。"""
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


class WebSearchTool(Tool):
    """网络搜索：返回相关网页的标题、链接和摘要。"""

    name = "web_search"
    description = (
        "在网络搜索引擎上查询关键词，返回相关网页的标题、链接和内容摘要。"
        "用于收集公开信息、事实核查、追踪最新动态。搜索时建议使用中文关键词。"
    )
    inputs = {"query": {"type": "string", "description": "搜索关键词，应具体、可查证"}}
    output_type = "string"

    def __init__(self, provider: str = "bing", tavily_api_key: Optional[str] = None, max_results: int = 6, timeout: int = 25):
        super().__init__()
        self.provider = provider
        self.tavily_api_key = tavily_api_key
        self.max_results = max_results
        self.timeout = timeout
        if provider == "tavily" and not tavily_api_key:
            raise ValueError("Tavily 需要 TAVILY_API_KEY")

    def forward(self, query: str) -> str:
        if self.provider == "tavily":
            return self._tavily(query)
        return self._bing(query)

    # ---------- Bing 国内版（免费、直连） ----------

    def _bing(self, query: str) -> str:
        url = "https://cn.bing.com/search?q=" + requests.utils.quote(query)
        try:
            resp = requests.get(url, timeout=self.timeout, headers=_BING_HEADERS)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            return f"Bing 搜索失败: {e}"

        try:
            doc = lh.fromstring(resp.text)
            items = doc.xpath('//li[contains(@class, "b_algo")]')[: self.max_results]
        except Exception as e:  # noqa: BLE001
            return f"解析搜索结果失败: {e}"

        if not items:
            return "没有搜到结果，请换关键词重试。"

        lines = []
        for i, it in enumerate(items, 1):
            a = it.xpath('.//h2/a')
            if not a:
                continue
            a = a[0]
            title = a.text_content().strip()
            href = a.get("href", "")
            cap = it.xpath('.//div[contains(@class, "b_caption")]/p')
            snip = cap[0].text_content().strip()[:200] if cap else ""
            lines.append(f"[{i}] {title}\n    链接: {href}\n    摘要: {snip}")
        return "\n\n".join(lines) if lines else "解析到 0 条有效结果，请换关键词重试。"

    # ---------- Tavily（需 key，质量高） ----------

    def _tavily(self, query: str) -> str:
        try:
            from tavily import TavilyClient
        except ImportError:
            return "错误：未安装 tavily-python"

        try:
            resp = TavilyClient(api_key=self.tavily_api_key).search(
                query=query, max_results=self.max_results, search_depth="basic"
            )
        except Exception as e:  # noqa: BLE001
            return f"搜索失败: {e}"

        results = resp.get("results", [])
        if not results:
            return "没有搜到结果，请换关键词重试。"

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(
                f"[{i}] {r.get('title', '')}\n    链接: {r.get('url', '')}\n    摘要: {(r.get('content') or '')[:200]}"
            )
        return "\n\n".join(lines)


class FetchPageTool(Tool):
    """抓取网页正文，转成纯文本（截断到 max_chars 字符）。"""

    name = "fetch_page"
    description = (
        "抓取指定 URL 的网页正文并转为纯文本。"
        "当 web_search 返回的摘要不够时，用此工具读取全文。"
    )
    inputs = {"url": {"type": "string", "description": "要抓取的完整网址（http/https）"}}
    output_type = "string"

    def __init__(self, timeout: int = 20, max_chars: int = 6000):
        super().__init__()
        self.timeout = timeout
        self.max_chars = max_chars

    def forward(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "错误：URL 必须以 http:// 或 https:// 开头"
        try:
            resp = requests.get(url, timeout=self.timeout, headers=_BING_HEADERS, allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            return f"抓取失败: {e}"
        return _clean_html(resp.text, self.max_chars)


def build_search_tools(search_provider: str, tavily_api_key: Optional[str]) -> list[Tool]:
    return [WebSearchTool(provider=search_provider, tavily_api_key=tavily_api_key), FetchPageTool()]
