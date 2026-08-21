"""测试公共工具：FakeModel / FakeResponse。

不依赖真实 API，按 smolagents 的接口约定模拟：
- Agent 内部走 model.generate()（HANDOVER 踩坑笔记：双入口都要支持）
- 节点代码走 model([...])（__call__）
"""


class FakeResponse:
    """模拟模型返回值：只有 content 属性被消费。"""

    def __init__(self, content: str):
        self.content = content


class FakeModel:
    """按顺序吐出预设响应的假模型。

    responses 用完后继续调用会 IndexError——测试里应保证数量匹配，
    多出来的调用本身就是 bug（说明节点多调了模型）。
    """

    model_id = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.messages = []  # 记录每次调用的消息列表，供断言提示词内容

    def __call__(self, messages, **kwargs):
        self.calls += 1
        self.messages.append(messages)
        return FakeResponse(self.responses.pop(0))

    def generate(self, messages, **kwargs):
        self.calls += 1
        self.messages.append(messages)
        return FakeResponse(self.responses.pop(0))
