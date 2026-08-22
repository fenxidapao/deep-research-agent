"""工具层测试：Bing 解析（mock 响应，不碰网络）+ HTML 清洗 + URL 校验 + 调用统计埋点。"""

import requests

from deep_research.tools import (
    CourseRetrieveTool,
    FetchPageTool,
    WebSearchTool,
    _clean_html,
    get_tool_stats,
    reset_tool_stats,
)

BING_HTML = """
<html><body><ol id="b_results">
<li class="b_algo">
  <h2><a href="https://example.com/1">第一条标题</a></h2>
  <div class="b_caption"><p>第一条摘要内容。</p></div>
</li>
<li class="b_algo">
  <h2><a href="https://example.com/2">第二条标题</a></h2>
  <div class="b_caption"><p>第二条摘要内容。</p></div>
</li>
</ol></body></html>
"""

EMPTY_HTML = "<html><body><ol id='b_results'></ol></body></html>"


class _FakeResp:
    """假 requests.Response：只有工具用到的 text / raise_for_status。"""

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class TestCleanHtml:
    def test_strips_script_style_and_tags(self):
        raw = "<script>var x = 1;</script><style>.a{}</style><p>Hello <b>World</b></p>"
        assert _clean_html(raw) == "Hello World"

    def test_unescapes_entities(self):
        assert _clean_html("<p>a &amp; b &lt; c</p>") == "a & b < c"

    def test_truncates_to_max_chars(self):
        raw = "<p>" + "字" * 100 + "</p>"
        assert len(_clean_html(raw, max_chars=20)) == 20


class TestBingParse:
    def test_parses_results(self, monkeypatch):
        monkeypatch.setattr("deep_research.tools.requests.get", lambda *a, **k: _FakeResp(BING_HTML))
        out = WebSearchTool(provider="bing").forward("测试关键词")
        assert "第一条标题" in out
        assert "https://example.com/1" in out
        assert "第一条摘要内容" in out
        assert "第二条标题" in out

    def test_respects_max_results(self, monkeypatch):
        monkeypatch.setattr("deep_research.tools.requests.get", lambda *a, **k: _FakeResp(BING_HTML))
        out = WebSearchTool(provider="bing", max_results=1).forward("测试关键词")
        assert "第一条标题" in out
        assert "第二条标题" not in out

    def test_no_results_message(self, monkeypatch):
        monkeypatch.setattr("deep_research.tools.requests.get", lambda *a, **k: _FakeResp(EMPTY_HTML))
        out = WebSearchTool(provider="bing").forward("不存在的词")
        assert "没有搜到结果" in out

    def test_request_error_message(self, monkeypatch):
        def boom(*a, **k):
            raise requests.ConnectionError("连接失败")

        monkeypatch.setattr("deep_research.tools.requests.get", boom)
        out = WebSearchTool(provider="bing").forward("测试")
        assert "Bing 搜索失败" in out

    def test_parse_error_message(self, monkeypatch):
        monkeypatch.setattr("deep_research.tools.requests.get", lambda *a, **k: _FakeResp("<html><broken"))
        out = WebSearchTool(provider="bing").forward("测试")
        assert "解析搜索结果失败" in out or "没有搜到结果" in out

    def test_tavily_requires_key(self):
        import pytest

        with pytest.raises(ValueError):
            WebSearchTool(provider="tavily", tavily_api_key=None)


class TestFetchPage:
    def test_rejects_non_http_url(self):
        out = FetchPageTool().forward("ftp://example.com/x")
        assert "http" in out

    def test_cleans_fetched_page(self, monkeypatch):
        monkeypatch.setattr(
            "deep_research.tools.requests.get",
            lambda *a, **k: _FakeResp("<html><script>x</script><p>正文内容</p></html>"),
        )
        out = FetchPageTool().forward("https://example.com/x")
        assert out == "正文内容"

    def test_fetch_error_message(self, monkeypatch):
        def boom(*a, **k):
            raise requests.Timeout("超时")

        monkeypatch.setattr("deep_research.tools.requests.get", boom)
        out = FetchPageTool().forward("https://example.com/x")
        assert "抓取失败" in out


class TestToolStats:
    """T-3 埋点：工具调用次数/失败/无结果统计（每次先清零，互不干扰）。"""

    def test_success_records_call(self, monkeypatch):
        reset_tool_stats()
        monkeypatch.setattr("deep_research.tools.requests.get", lambda *a, **k: _FakeResp(BING_HTML))
        WebSearchTool(provider="bing").forward("测试")
        s = get_tool_stats()["web_search"]
        assert s["calls"] == 1
        assert s["fail"] == 0
        assert s["no_result"] == 0

    def test_fail_records_fail(self, monkeypatch):
        reset_tool_stats()

        def boom(*a, **k):
            raise requests.ConnectionError("网络错误")

        monkeypatch.setattr("deep_research.tools.requests.get", boom)
        WebSearchTool(provider="bing").forward("测试")
        s = get_tool_stats()["web_search"]
        assert s["calls"] == 1
        assert s["fail"] == 1

    def test_no_result_records_separately(self, monkeypatch):
        reset_tool_stats()
        monkeypatch.setattr("deep_research.tools.requests.get", lambda *a, **k: _FakeResp(EMPTY_HTML))
        WebSearchTool(provider="bing").forward("x")
        s = get_tool_stats()["web_search"]
        assert s["calls"] == 1
        assert s["fail"] == 0
        assert s["no_result"] == 1  # 成功执行但无结果，不算失败

    def test_fetch_page_stats(self):
        reset_tool_stats()
        FetchPageTool().forward("ftp://x")  # URL 非法 → fail
        s = get_tool_stats()["fetch_page"]
        assert s["calls"] == 1
        assert s["fail"] == 1

    def test_reset_clears_all(self, monkeypatch):
        reset_tool_stats()
        monkeypatch.setattr("deep_research.tools.requests.get", lambda *a, **k: _FakeResp(BING_HTML))
        WebSearchTool(provider="bing").forward("a")
        reset_tool_stats()
        assert all(v["calls"] == 0 for v in get_tool_stats().values())


# ---------- CourseRAG 集成工具（course_retrieve） ----------


class _FakeJsonResp:
    """假 requests.Response：返回预置 JSON（.json() 供工具消费）。"""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


RETRIEVE_HITS = {
    "query": "什么是红黑树",
    "mode": "accurate",
    "docs": [
        {
            "rank": 1,
            "source": "数据结构笔记.md",
            "content": "红黑树是一种自平衡二叉查找树，性质包括根为黑、红节点的子节点为黑…",
            "score": 0.8123,
            "start_index": 120,
        },
        {
            "rank": 2,
            "source": "数据结构笔记.md",
            "content": "插入时通过旋转与变色维持平衡…",
            "score": 0.6543,
            "start_index": 800,
        },
    ],
}

RETRIEVE_EMPTY = {"query": "x", "mode": "accurate", "docs": []}


class TestCourseRetrieve:
    def test_hits_formatted_with_source_and_score(self, monkeypatch):
        monkeypatch.setattr("deep_research.tools.requests.post", lambda *a, **k: _FakeJsonResp(RETRIEVE_HITS))
        out = CourseRetrieveTool(base_url="http://127.0.0.1:8001").forward("什么是红黑树")
        assert "课程知识库命中 2 条" in out
        assert "数据结构笔记.md" in out
        assert "0.8123" in out
        assert "红黑树是一种自平衡二叉查找树" in out

    def test_respects_top_k(self, monkeypatch):
        monkeypatch.setattr("deep_research.tools.requests.post", lambda *a, **k: _FakeJsonResp(RETRIEVE_HITS))
        out = CourseRetrieveTool(base_url="http://127.0.0.1:8001", top_k=1).forward("q")
        assert "[1] 来源" in out
        assert "[2] 来源" not in out

    def test_no_hits_message(self, monkeypatch):
        monkeypatch.setattr("deep_research.tools.requests.post", lambda *a, **k: _FakeJsonResp(RETRIEVE_EMPTY))
        out = CourseRetrieveTool().forward("无关问题")
        assert "未命中" in out

    def test_service_down_degrades_gracefully(self, monkeypatch):
        def boom(*a, **k):
            raise requests.ConnectionError("连接被拒绝")

        monkeypatch.setattr("deep_research.tools.requests.post", boom)
        out = CourseRetrieveTool(base_url="http://127.0.0.1:8001").forward("q")
        assert "课程知识库检索失败" in out
        assert "web_search" in out  # 提示降级路径

    def test_stats_recorded(self, monkeypatch):
        reset_tool_stats()
        monkeypatch.setattr("deep_research.tools.requests.post", lambda *a, **k: _FakeJsonResp(RETRIEVE_HITS))
        CourseRetrieveTool().forward("q")
        s = get_tool_stats()["course_retrieve"]
        assert s["calls"] == 1
        assert s["fail"] == 0

    def test_posts_accurate_mode_by_default(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["json"] = json
            return _FakeJsonResp(RETRIEVE_EMPTY)

        monkeypatch.setattr("deep_research.tools.requests.post", fake_post)
        CourseRetrieveTool().forward("q")
        assert captured["json"]["mode"] == "accurate"
        assert captured["json"]["question"] == "q"
