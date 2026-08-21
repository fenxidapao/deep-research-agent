"""经验沉淀：把失败/教训写入 JSON 文件，后续任务规划时读取复用。

闭环：Executor 执行失败 → record() 落盘 → 下次同类任务 Planner 规划时
relevant() 注入相关经验 → 避免重蹈覆辙。

纯本地文件，无模型/网络依赖；文件损坏/写入失败一律容错，不阻塞主流程。
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

_STOPWORDS = {"的", "了", "在", "是", "与", "和", "等", "一个", "这个", "以及", "进行"}


class ExperienceMemory:
    """经验库：JSON 文件存储，支持追加、相关检索、损坏容错。"""

    def __init__(self, path: str = "memory/experiences.json"):
        self.path = Path(path)
        self._entries: list[dict] = []
        self.load()

    # ---------- 读写 ----------

    def load(self) -> None:
        """读入全部经验；文件不存在/损坏时置空（不抛异常）。"""
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._entries = [e for e in data if isinstance(e, dict)]
        except (json.JSONDecodeError, OSError):
            self._entries = []

    def persist(self) -> None:
        """原子落盘（写临时文件后替换），失败静默——经验丢失不影响主流程。"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError:
            pass

    def add(self, domain: str, lesson: str, suggestion: str) -> None:
        """追加一条经验并落盘。"""
        self._entries.append(
            {
                "id": len(self._entries) + 1,
                "domain": domain,
                "lesson": lesson,
                "suggestion": suggestion,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self.persist()

    # ---------- 检索 ----------

    def relevant(self, query: str, top_k: int = 3) -> list[dict]:
        """按关键词重叠打分，返回与 query 最相关的经验（降序）。"""
        words = self._keywords(query)
        if not words:
            return []
        scored = []
        for e in self._entries:
            text = f"{e.get('domain', '')} {e.get('lesson', '')} {e.get('suggestion', '')}"
            hit = sum(1 for w in words if w in text)
            if hit:
                scored.append((hit, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    @staticmethod
    def _keywords(text: str) -> list[str]:
        """粗粒度关键词提取：英文单词（≥2 字母）+ 中文滑窗 n-gram（2~4 字），去停用词。

        滑窗保证"巴黎奥运会"同时产出"巴黎""奥运""巴黎奥运"等片段，
        避免贪婪匹配把长词拆碎导致检索丢失。
        """
        words = set(re.findall(r"[a-zA-Z]{2,}", text.lower()))
        for seg in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            for n in (2, 3, 4):
                for i in range(len(seg) - n + 1):
                    words.add(seg[i : i + n])
        return [w for w in words if w not in _STOPWORDS]

    # ---------- 工具 ----------

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        """清空经验（测试/运维用）。"""
        self._entries = []
        self.persist()
