# Deep Research Agent（深度研究助手）

> LangGraph 编排 + smolagents 内核的「规划-执行-反思」三节点 Agent。
> 输入一个问题，自动规划 → 多轮搜索 → 反思 → 输出带来源引用的结构化研究报告。

## 架构

```
                        ┌──────────────┐
   用户任务 ────────────▶│   Planner    │  拆解调研简报 + 步骤列表（JSON）
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
     ┌──────────────────│   Executor   │  smolagents CodeAgent：写代码调用
     │    continue      └──────┬───────┘  搜索/抓网页工具，产出研究笔记
     │                         ▼
     │                  ┌──────────────┐
     │                  │  Reflector   │  评估进度：continue / replan / complete
     │                  └──────┬───────┘
     │            replan       │  complete
     │   ┌─────────────────────┼──────────────┐
     │   ▼                     ▼              ▼
     │  回 Planner（带已有进展）          ┌──────────────┐
     │                               │    Writer    │  汇总笔记写最终报告
     └───────────────────────────────┴──────┬───────┘
                                             ▼
                                        Markdown 报告
```

- **编排层**：LangGraph `StateGraph`，显式三节点 + 条件边回环，`MemorySaver` 支持断点续跑（同一 `thread_id` 可恢复）。
- **执行层**：smolagents `CodeAgent`（代码执行式 Agent，可写 Python 循环搜索、分析中间结果）。
- **模型**：DeepSeek API 为主（OpenAI 兼容接口），Ollama 本地模型降级。
- **搜索**：Bing 国内版（自研 HTML 解析，免费直连）/ Tavily（可选，质量更高）。

## 特性

- ✅ 三节点循环：Plan → Execute → Reflect，Reflector 可触发**重规划**（replan）修正方向
- ✅ 断点续跑：`thread_id` 维度 Checkpoint，长任务中断可恢复
- ✅ 防重复搜索：`search_history` 状态跟踪，避免同一关键词反复搜
- ✅ 预算护栏：步骤数/循环轮数/单步搜索次数硬上限，防止失控
- ✅ 中文优先：针对国内环境优化（Bing 搜索、中文提示词、DeepSeek 模型）

## 快速启动

```bash
# 1. 环境
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows
# source .venv/bin/pip install -r requirements.txt   # macOS/Linux

# 2. 配置（复制后填入 DeepSeek API key，https://platform.deepseek.com）
cp .env.example .env

# 3. 运行
.venv/Scripts/python main.py "2024年巴黎奥运会中国代表团获得多少枚金牌？排名第几？"
```

## 使用示例

```bash
# 换模型 / 换搜索源
python main.py "对比 DeepSeek-V3 与 GPT-4o" --model deepseek --search bing

# 脚本化输出（JSON）
python main.py "星露谷物语 1.6 新增内容" --json

# 评测
python evaluate.py                     # 全量评测集（自动断点续跑，中断不丢）
python evaluate.py --limit 5           # 前 5 条快速验证
python evaluate.py --fresh             # 清空进度重跑全部

# FastAPI 服务
uvicorn api:app --port 8000
curl -X POST http://localhost:8000/run -H "Content-Type: application/json" -d '{"task": "..."}'
```

## 评测结果

> 16 条评测集（多源综合 + 事实核查），DeepSeek-v4-flash + Bing 搜索，全自动打分（关键词命中）。
> 详细数据见 `eval_set/metrics.json`。

| 指标 | 数值 |
|---|---|
| 规划成功率 | 100% |
| 报告完成率 | 100%（16/16 全部产出报告） |
| 答案命中率 | 98% |
| 平均执行步骤 / 循环轮数 | 3.6 步 / 3.1 轮 |
| 平均耗时 | 7.1 分钟/条（搜索为主要耗时，Bing 单次约 11s） |
| 总耗时 | 16 条约 1.9 小时 |

> 说明：13/16 条关键词全命中；唯一 0.67 为 RTX 4060 题（8GB/1080p 三词中漏一词）。
> 评测中暴露并修复的问题：DeepSeek API 偶发空输出 → Writer 三重试兜底；CodeAgent 代码执行超时默认 30s 不足 → 放宽至 180s。

## 项目结构

```
agent/
├── deep_research/
│   ├── graph.py            # LangGraph 组装 + 条件路由 + Checkpoint
│   ├── state.py            # State 定义（步骤/结果/反思/报告）
│   ├── prompts.py          # Planner/Reflector/Writer 提示词
│   ├── tools.py            # Bing/Tavily 搜索 + 网页抓取（smolagents Tool）
│   ├── model.py            # DeepSeek / Ollama 模型工厂
│   └── nodes/
│       ├── planner.py      # 拆解任务为简报 + 步骤
│       ├── executor.py     # smolagents CodeAgent 执行单步研究
│       ├── reflector.py    # 判定 continue/replan/complete
│       └── writer.py       # 汇总笔记生成 Markdown 报告
├── main.py                 # CLI
├── api.py                  # FastAPI 接口
├── evaluate.py             # 量化评测脚本
└── eval_set/tasks.json     # 16 条带参考答案的评测集
```

## 参考与改动

| 参考项目 | 借鉴点 | 本项目改动 |
|---|---|---|
| [open_deep_research](https://github.com/langchain-ai/open_deep_research) | 规划-反思循环思路、State 流转 | 显式三节点 + 条件边；执行体换成 smolagents CodeAgent；中文/Bing/DeepSeek 适配 |
| [smolagents](https://github.com/huggingface/smolagents) | CodeAgent 代码执行式 Agent | 作为 Executor 内核，封装搜索/抓取工具 |
| [langgraph](https://github.com/langchain-ai/langgraph) | StateGraph / MemorySaver | 编排骨架 |

> 原则：只借内核，不借全家桶。Planner/Reflector/Writer 提示词与节点逻辑全部自研。

## 路线图

- [ ] Supervisor 多子 Agent 并行研究
- [ ] 向量记忆（Chroma）沉淀长期经验
- [ ] Docker 部署
