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
| 单任务 token 消耗 | 约 21~32 万（有反思模式） |
| 断点恢复 | 中断后恢复仅需 18.4s（占全流程 7%，无需重跑研究过程） |

> 说明：13/16 条关键词全命中；唯一 0.67 为 RTX 4060 题（8GB/1080p 三词中漏一词）。
> 评测中暴露并修复的问题：DeepSeek API 偶发空输出 → Writer 三重试兜底；CodeAgent 代码执行超时默认 30s 不足 → 放宽至 180s。

### 反思前后对照（ablation，3 条小样本）

| 任务 | 有反思命中 | 无反思命中 | token 差异 | 耗时差异 |
|---|---|---|---|---|
| 对比题（#1） | 0.67（3步早停） | 1.0（跑满5步） | -36% | -42% |
| 兴趣题（#3） | 1.0 | 1.0 | -29% | -13% |
| 事实题（#15） | 1.0 | 1.0 | +36% | +112% |

**结论（如实）**：反思的价值在**效率**而非准确率——Reflector 的早停/精简平均省约 30% token 与耗时；但 #1 因过早 complete（第一轮即判定收尾）漏掉关键词，命中率 -0.11。改进方向：提高 Reflector 的 complete 阈值（如要求覆盖全部计划步骤或关键维度再收尾）。样本量小，结论为初步观察。

## 生产化设计

> 面向"可部署、可维护、可演进"的工程化设计，而非一次性脚本。对应代码：`deep_research/` 包 + `tests/`（39 个用例，全部 mock，秒级跑完，不依赖真实 API/网络）。

### 预算护栏（防失控）

| 护栏 | 实现 | 配置项 |
|---|---|---|
| 计划步数上限 | Planner 单次最多产出 `max_plan_steps` 步 | `MAX_PLAN_STEPS` |
| 循环轮数上限 | Reflector 达 `max_iterations` 强制收尾 | `MAX_ITERATIONS` |
| 单步搜索上限 | CodeAgent `max_steps` 限制单步工具调用 | `MAX_SEARCHES_PER_STEP` |
| 报告长度上限 | Writer 输出截断 | `MAX_REPORT_LENGTH` |
| 单步执行超时 | CodeAgent 代码执行 180s 超时 | `executor_kwargs` |

> ⚠️ 已知遗留项：Planner 重规划时将 `iteration` 重置为 0，导致 `max_iterations` 护栏在 replan 循环下失效（步骤/搜索仍受 current_step 与 max_steps 兜底，不会无限运行，但轮数不累计）。待修。

### 断点续跑（长任务不重跑）

- LangGraph `MemorySaver` + `thread_id`：中断后同一 thread_id 续跑，已完成的研究步骤不重跑
- 实测：中断恢复仅 18.4s，占全流程 7%（评测 #15）
- 评测脚本 `evaluate.py` 实时落盘 `progress.jsonl`，中断后自动跳过已完成任务

### 容错策略

| 故障 | 处理 |
|---|---|
| 模型偶发空输出 | Writer 三重试，最终兜底输出研究笔记原文（HANDOVER 踩坑 #5） |
| Planner 输出非 JSON | `_extract_json` 容错解析（容忍代码块/前后杂质）；失败兜底为单步计划 |
| Reflector 输出异常 | 默认 continue，不中断流程 |
| 单步执行异常 | 记录失败原因，交由 Reflector 决定重规划或跳过 |
| 搜索失败/解析失败 | 返回可读错误文案，CodeAgent 自行换词重试 |

### 成本控制

- 默认 DeepSeek-v4-flash（便宜）+ Bing 免费直连：全项目 16 条评测约 5~6 元
- `UsageCounter` 精确统计每次调用的 input/output token（双入口：`__call__` + `generate()`），评测输出单任务 21~32 万 token
- 反思模式平均省约 30% token/耗时（见上方 ablation 表）

### 搜索降级链

```
Bing（免费直连） → Tavily（需 key，质量更高） → Ollama 本地（离线）
```

- 搜索：`SEARCH_PROVIDER=bing/tavily`
- 模型：`MODEL_PROVIDER=deepseek/ollama`，Ollama 走本地 OpenAI 兼容接口，断网可用

### 测试

```bash
.venv/Scripts/python -m pytest tests/ -q    # 39 passed，全 mock，约 1s
```

覆盖：`_extract_json` 容错、`UsageCounter` 计数、Bing 解析（mock HTML）、`_route` 三路由、Writer 空输出重试、mock 全链路端到端（含 replan 循环）。

## 项目结构

```
agent/
├── deep_research/
│   ├── graph.py            # LangGraph 组装 + 条件路由 + Checkpoint
│   ├── state.py            # State 定义（步骤/结果/反思/报告）
│   ├── prompts.py          # Planner/Reflector/Writer 提示词
│   ├── tools.py            # Bing/Tavily 搜索 + 网页抓取（smolagents Tool）
│   ├── model.py            # DeepSeek / Ollama 模型工厂 + UsageCounter
│   └── nodes/
│       ├── planner.py      # 拆解任务为简报 + 步骤
│       ├── executor.py     # smolagents CodeAgent 执行单步研究
│       ├── reflector.py    # 判定 continue/replan/complete
│       └── writer.py       # 汇总笔记生成 Markdown 报告
├── tests/                  # 39 个 pytest 用例（全 mock，不调真实 API）
│   ├── helpers.py          # FakeModel 测试替身
│   ├── test_planner.py     # _extract_json 容错 + 兜底
│   ├── test_model.py       # UsageCounter / _CountingModel 双入口
│   ├── test_tools.py       # Bing 解析（mock HTML）+ 网页抓取
│   ├── test_graph.py       # _route 三路由
│   ├── test_writer.py      # Writer 空输出重试 + 兜底
│   └── test_e2e.py         # mock 全链路端到端（含 replan 循环）
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
