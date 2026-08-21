"""模型层测试：UsageCounter 计数 + _CountingModel 双入口包装。"""

from types import SimpleNamespace

from deep_research.model import UsageCounter, _CountingModel


class _Resp:
    def __init__(self, inp, out):
        self.token_usage = SimpleNamespace(input_tokens=inp, output_tokens=out)


class _RespNoUsage:
    token_usage = None


class _Inner:
    """真实模型替身：__call__ 与 generate 返回不同用量，用于验证双入口都计数。"""

    model_id = "real-model"

    def __call__(self, messages, **kwargs):
        return _Resp(1, 2)

    def generate(self, messages, **kwargs):
        return _Resp(3, 4)


class TestUsageCounter:
    def test_accumulates(self):
        c = UsageCounter()
        c.add(100, 50)
        c.add(10, 5)
        assert c.input_tokens == 110
        assert c.output_tokens == 55
        assert c.total_tokens == 165

    def test_none_safe(self):
        c = UsageCounter()
        c.add(None, None)
        assert c.input_tokens == 0
        assert c.output_tokens == 0
        assert c.total_tokens == 0

    def test_starts_at_zero(self):
        assert UsageCounter().total_tokens == 0


class TestCountingModel:
    def test_both_entries_counted(self):
        c = UsageCounter()
        cm = _CountingModel(_Inner(), c)
        cm([{"role": "user", "content": "x"}])       # 1 + 2
        cm.generate([{"role": "user", "content": "x"}])  # 3 + 4
        assert c.input_tokens == 4
        assert c.output_tokens == 6
        assert c.total_tokens == 10

    def test_missing_usage_not_counted(self):
        c = UsageCounter()

        class Inner:
            def __call__(self, m, **k):
                return _RespNoUsage()

            def generate(self, m, **k):
                return _RespNoUsage()

        cm = _CountingModel(Inner(), c)
        cm([{"role": "user", "content": "x"}])
        cm.generate([{"role": "user", "content": "x"}])
        assert c.total_tokens == 0

    def test_attribute_passthrough(self):
        cm = _CountingModel(_Inner(), UsageCounter())
        assert cm.model_id == "real-model"
