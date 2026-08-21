"""经验沉淀模块测试：落盘、检索、损坏容错、关键词提取。"""

import json

import pytest

from deep_research.memory import ExperienceMemory


@pytest.fixture
def mem(tmp_path):
    return ExperienceMemory(str(tmp_path / "experiences.json"))


class TestAddAndPersist:
    def test_add_persists_to_file(self, mem, tmp_path):
        mem.add("网页抓取", "目标网站返回 403", "换搜索引擎快照重试")
        saved = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
        assert len(saved) == 1
        assert saved[0]["lesson"] == "目标网站返回 403"
        assert saved[0]["created_at"]  # 带时间戳

    def test_reload_reads_back(self, mem):
        mem.add("数学建模", "Bing 搜索超时", "换关键词重试")
        fresh = ExperienceMemory(mem.path)  # 新实例从同一文件读回
        assert len(fresh) == 1
        assert fresh.relevant("数学建模")


class TestRelevant:
    def test_ranks_by_keyword_overlap(self, mem):
        mem.add("巴黎奥运会", "关键词过宽导致结果泛化", "拆成具体赛事名")
        mem.add("葡萄酒评价", "数据缺失", "查原始数据集")
        hits = mem.relevant("巴黎奥运会 金牌 数据")
        assert hits  # 有相关经验
        assert hits[0]["domain"] == "巴黎奥运会"

    def test_no_match_returns_empty(self, mem):
        mem.add("葡萄酒", "数据缺失", "查原始数据集")
        assert mem.relevant("完全无关的话题xyz") == []

    def test_empty_memory_returns_empty(self, mem):
        assert mem.relevant("任意话题") == []

    def test_top_k_limits(self, mem):
        for i in range(5):
            mem.add(f"主题{i}", "教训", "建议")
        hits = mem.relevant("主题 教训 建议", top_k=2)
        assert len(hits) <= 2


class TestRobustness:
    def test_missing_file_is_empty(self, tmp_path):
        m = ExperienceMemory(str(tmp_path / "nonexistent.json"))
        assert len(m) == 0

    def test_corrupted_file_tolerated(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{这不是合法JSON", encoding="utf-8")
        m = ExperienceMemory(str(f))
        assert len(m) == 0  # 不抛异常

    def test_non_list_json_tolerated(self, tmp_path):
        f = tmp_path / "obj.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        m = ExperienceMemory(str(f))
        assert len(m) == 0

    def test_clear(self, mem):
        mem.add("a", "b", "c")
        mem.clear()
        assert len(mem) == 0


class TestKeywords:
    def test_mixes_english_and_chinese(self):
        words = ExperienceMemory._keywords("如何用 Python 处理巴黎奥运会数据？")
        assert "python" in words
        assert "巴黎奥运" in words

    def test_stopwords_removed(self):
        words = ExperienceMemory._keywords("的 了 在 是 与 和 测试")
        assert "测试" in words
        assert "的" not in words
