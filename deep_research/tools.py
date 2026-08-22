"""搜索与抓取工具（smolagents Tool 格式）。

- web_search: bing（默认，国内直连免费，自研 HTML 解析）/ tavily（需 key，质量更高）
- fetch_page: 抓取网页正文转纯文本，供 CodeAgent 深度阅读

注：DuckDuckGo 国内不可达，已弃用。
"""

import html
import re
import threading
from typing import Optional

import requests
from lxml import html as lh
from smolagents import Tool

from .logging_utils import get_logger

logger = get_logger("tools")

_BING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ---------- 工具调用统计（T-3 埋点：量化"工具调用成功率"） ----------
# 模块级线程安全计数：calls 每次调用 +1；fail=错误返回；no_result=执行成功但无结果。
# 供评测脚本/CLI 汇总输出，不改变工具返回值与行为。

TOOL_STATS = {
    "web_search": {"calls": 0, "fail": 0, "no_result": 0},
    "fetch_page": {"calls": 0, "fail": 0, "no_result": 0},
    "course_retrieve": {"calls": 0, "fail": 0, "no_result": 0},
}
_STATS_LOCK = threading.Lock()


def _record(name: str) -> None:
    with _STATS_LOCK:
        TOOL_STATS[name]["calls"] += 1


def _mark(name: str, key: str) -> None:
    with _STATS_LOCK:
        TOOL_STATS[name][key] += 1


def get_tool_stats() -> dict:
    """返回统计快照（深拷贝，避免并发读脏）。"""
    with _STATS_LOCK:
        return {k: dict(v) for k, v in TOOL_STATS.items()}


def reset_tool_stats() -> None:
    """清零统计（评测开始前调用）。"""
    with _STATS_LOCK:
        for v in TOOL_STATS.values():
            v["calls"] = v["fail"] = v["no_result"] = 0


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
        _record("web_search")
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
            logger.warning("Bing 搜索失败: %s", e)
            _mark("web_search", "fail")
            return f"Bing 搜索失败: {e}"

        try:
            doc = lh.fromstring(resp.text)
            items = doc.xpath('//li[contains(@class, "b_algo")]')[: self.max_results]
        except Exception as e:  # noqa: BLE001
            _mark("web_search", "fail")
            return f"解析搜索结果失败: {e}"

        if not items:
            _mark("web_search", "no_result")
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
            _mark("web_search", "fail")
            return "错误：未安装 tavily-python"

        try:
            resp = TavilyClient(api_key=self.tavily_api_key).search(
                query=query, max_results=self.max_results, search_depth="basic"
            )
        except Exception as e:  # noqa: BLE001
            _mark("web_search", "fail")
            return f"搜索失败: {e}"

        results = resp.get("results", [])
        if not results:
            _mark("web_search", "no_result")
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
        _record("fetch_page")
        if not url.startswith(("http://", "https://")):
            _mark("fetch_page", "fail")
            return "错误：URL 必须以 http:// 或 https:// 开头"
        try:
            resp = requests.get(url, timeout=self.timeout, headers=_BING_HEADERS, allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            _mark("fetch_page", "fail")
            return f"抓取失败: {e}"
        return _clean_html(resp.text, self.max_chars)


def build_search_tools(search_provider: str, tavily_api_key: Optional[str]) -> list[Tool]:
    return [WebSearchTool(provider=search_provider, tavily_api_key=tavily_api_key), FetchPageTool()]


class CourseRetrieveTool(Tool):
    """私有知识库检索：调用 CourseRAG 服务的 /retrieve 端点（HTTP 解耦，零侵入）。

    设计背景：
    - Agent 是主角、RAG 是工具之一：研究题目涉及专业课知识（数据结构/组成原理/
      操作系统/数据库/计网等）时优先查本地课程库，能拿到带来源的原文块；
    - 走 HTTP 而非进程内导入，RAG 侧零改动，两个项目解耦部署；
    - RAG 服务不可达时返回错误说明（CodeAgent 会自行决定降级到 web_search），
      不阻塞主流程。
    """

    name = "course_retrieve"
    description = (
        "在私有课程知识库（数据结构/组成原理/操作系统/数据库/计算机网络等专业课）中检索问题，"
        "返回命中的原文块、来源文件名与相关性分数。"
        "当调研题目涉及专业课概念、术语定义、算法原理等课程内容时，优先使用本工具；"
        "与 web_search 互补：课程内容查本地库更准，时事/外部信息用 web_search。"
    )
    inputs = {
        "question": {"type": "string", "description": "检索问题（课程知识点，应具体）"},
        "mode": {
            "type": "string",
            "enum": ["accurate", "fast"],
            "nullable": True,
            "description": "accurate=向量+BM25 混合+重排（更准，较慢）；fast=纯向量（秒级）；默认 accurate",
        },
    }
    output_type = "string"

    def __init__(self, base_url: str = "http://127.0.0.1:8001", timeout: int = 20, top_k: int = 5):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.top_k = top_k

    def forward(self, question: str, mode: str = "accurate") -> str:
        _record("course_retrieve")
        try:
            resp = requests.post(
                f"{self.base_url}/retrieve",
                json={"question": question, "mode": mode},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("CourseRAG 检索失败: %s", e)
            _mark("course_retrieve", "fail")
            return f"课程知识库检索失败: {e}（可降级用 web_search）"

        docs = data.get("docs", [])
        if not docs:
            _mark("course_retrieve", "no_result")
            return "课程知识库未命中相关内容，请改换措辞或用 web_search。"

        lines = []
        for d in docs[: self.top_k]:
            source = d.get("source", "?")
            score = d.get("score")
            content = (d.get("content") or "").strip().replace("\n", " ")[:400]
            score_str = f"{score:.4f}" if score is not None else "n/a"
            lines.append(f"[{d.get('rank', 0)}] 来源: {source} | 相关度: {score_str}\n    内容: {content}")
        return "课程知识库命中 " + str(len(docs)) + " 条：\n\n" + "\n\n".join(lines)
