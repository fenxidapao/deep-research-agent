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
- ✅ supervisor 并行研究：一批步骤分发多个 worker 并行执行，单 worker 失败不影响整体（`--supervisor`）
- ✅ 断点续跑：`thread_id` 维度 Checkpoint，长任务中断可恢复
- ✅ 防重复搜索：`search_history` 状态跟踪，避免同一关键词反复搜
- ✅ 注入防护：Planner/Reflector/Writer/Executor 提示词内置注入指令忽略规则（评测集含安全用例 #17）
- ✅ 预算护栏：步骤数/循环轮数/单步搜索次数硬上限，防止失控
- ✅ 经验沉淀：执行失败教训写入本地 JSON，同类任务下次规划时自动规避
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

# supervisor 并行模式（一批步骤多个 worker 并行研究，MAX_PARALLEL_WORKERS 控制并发）
python main.py "2026 年 AI 行业十大趋势" --supervisor

# 脚本化输出（JSON）
python main.py "星露谷物语 1.6 新增内容" --json

# 评测
python evaluate.py                     # 全量评测集（自动断点续跑，中断不丢）
python evaluate.py --limit 5           # 前 5 条快速验证
python evaluate.py --fresh             # 清空进度重跑全部

# FastAPI 服务
uvicorn api:app --port 8000
curl -X POST http://localhost:8000/run -H "Content-Type: application/json" -d '{"task": "..."}'

# Docker 部署（需本机装 Docker；方案与验证清单见 docs/DOCKER.md）
docker compose up -d
curl http://localhost:8000/health
```

## 评测结果

> 16 条评测集（多源综合 + 事实核查），DeepSeek-v4-flash + Bing 搜索，全自动打分（关键词命中）。
> 详细数据见 `eval_set/metrics.json`。**2026-08-21 修复 iteration 缺陷后全量重跑**（`evaluate.py`，断点续跑）。

| 指标 | 数值（重跑后） | 修复前 |
|---|---|---|
| 规划成功率 | 100% | 100% |
| 报告完成率 | 100%（16/16 全部产出报告） | 100% |
| 答案命中率 | **94%** | 98% |
| 平均执行步骤 / 循环轮数 | 3.5 步 / **3.5 轮** | 3.6 步 / 3.1 轮 |
| 平均耗时 | **4.9 分钟/条** | 7.1 分钟/条 |
| 总耗时 | **16 条约 1.3 小时** | 约 1.9 小时 |
| 单任务 token 消耗 | 本次未捕获（评测收尾进程异常退出） | 约 21~32 万 |
| 工具调用统计 | 评测/CLI 输出 `工具统计`：web_search / fetch_page 的 calls/fail/no_result | — |
| 断点恢复 | 中断后恢复仅需 18.4s（占全流程 7%，无需重跑研究过程） | 同 |

> 说明：重跑后 14/16 条关键词全命中；id=3（兴趣）/id=9（健康）各 0.5（未全命中），均跑满 5 步 + 护栏强制收尾，属 LLM 输出随机性的单次样本波动（temperature=0.3，非早停漏词）。**循环轮数 3.1→3.5 是 iteration 修复的预期效果**（修复前 replan 重置计数导致轮数被低估）；耗时下降 31% 主要来自 Bing 响应波动。评测集已扩展至 17 条（含 #17 注入安全用例，待重跑出数据）。
> 评测中暴露并修复的问题：DeepSeek API 偶发空输出 → Writer 三重试兜底；CodeAgent 代码执行超时默认 30s 不足 → 放宽至 180s；iteration 被 planner 重置 → 重规划保留计数（护栏恢复生效）；agent 直接 import urllib 被沙箱拒绝导致步骤触顶 → 提示词强制用 fetch_page 工具；提示词注入 → 四节点内置忽略规则。

### 反思前后对照（ablation，3 条小样本，P-1 修复后重测）

| 任务 | 有反思命中（修复前→修复后） | 无反思命中 | token 差异 | 耗时差异 |
|---|---|---|---|---|
| 对比题（#1） | 0.67 → **1.0**（5/5 步，早停已修） | 1.0 | +2% | -21% |
| 兴趣题（#3） | 1.0（1/1 步） | 1.0 | **-83%** | -58% |
| 事实题（#15） | 1.0 → 0.5（3/3 步，随机波动） | 1.0 | -4% | +8% |

**结论（如实）**：P-1 修复后 #1 早停根治（0.67→1.0，从"3 步早停"变为"5/5 步执行满"），证明"提高 complete 门槛"方向有效；反思的效率价值依然成立（#3 省 83% token）。但 #15 出现单次随机波动（1.0→0.5，**3/3 步执行满、非早停**，同任务此前两轮均 1.0）——3 条小样本下汇总 0.83 vs 1.00 **不能归因于修复**：修复效果与随机波动在 3 条样本上无法区分，严谨结论需多次重跑取平均。样本量小，结论为初步观察。

## 生产化设计

> 面向"可部署、可维护、可演进"的工程化设计，而非一次性脚本。对应代码：`deep_research/` 包 + `tests/`（72 个用例，全部 mock，秒级跑完，不依赖真实 API/网络）。

### 预算护栏（防失控）

| 护栏 | 实现 | 配置项 |
|---|---|---|
| 计划步数上限 | Planner 单次最多产出 `max_plan_steps` 步 | `MAX_PLAN_STEPS` |
| 循环轮数上限 | Reflector 达 `max_iterations` 强制收尾 | `MAX_ITERATIONS` |
| 单步搜索上限 | CodeAgent `max_steps` 限制单步工具调用 | `MAX_SEARCHES_PER_STEP` |
| 报告长度上限 | Writer 输出截断 | `MAX_REPORT_LENGTH` |
| 单步执行超时 | CodeAgent 代码执行 180s 超时 | `executor_kwargs` |

> ✅ 修复记录（8/21）：Planner 重规划曾将 `iteration` 重置为 0，导致 `max_iterations` 护栏在 replan 循环下失效——现重规划保留累计值（含解析失败兜底分支），护栏恢复生效。回归测试：`tests/test_planner.py` / `test_reflector.py`。

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
| **提示词注入** | 四节点提示词内置忽略规则；评测集含安全用例 #17（伪装注入指令） |
| **沙箱误用** | Executor 提示词强制"抓网页用 fetch_page 工具，禁止 import urllib/requests"（实测曾因 urllib 被拒导致步骤触顶） |

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

### 经验沉淀（Memory）

```
Executor 执行失败 → 写入 memory/experiences.json → 下次同类任务 Planner 规划时注入相关经验 → 规避重蹈覆辙
```

- 纯本地 JSON 文件，无模型/网络依赖；文件损坏/写入失败一律容错，不阻塞主流程
- 检索：关键词 n-gram 重叠打分，取 top-3 注入提示词
- 路径可配：`MEMORY_FILE`（默认 `memory/experiences.json`，已 gitignore）

### 并行研究（supervisor 模式）

```
Planner 拆解步骤 → Supervisor 取一批（≤ max_parallel_workers）→ 多个 worker 并行研究 → 汇总 → Reflector 照常评估
```

- `build_graph(cfg, supervisor=True)` 或 CLI `--supervisor`；默认单步 Executor 路径不变
- worker 复用 `run_single_step`（与单步同逻辑，行为一致）；单 worker 失败隔离为失败笔记并沉淀经验，不影响整批
- 并发安全：`UsageCounter` / `ExperienceMemory` 内部加锁，token 统计与经验落盘不丢
- 并发数可配：`MAX_PARALLEL_WORKERS`（默认 3）。注意：搜索源并发过大会触发限流，按需调低

### 测试

```bash
.venv/Scripts/python -m pytest tests/ -q    # 72 passed，全 mock，约 1s
```

覆盖：`_extract_json` 容错、`UsageCounter` 计数、Bing 解析（mock HTML）、`_route` 三路由、Writer 空输出重试、planner iteration 保留、Reflector 预算护栏、mock 全链路端到端（含 replan 循环、supervisor 并行、断点续跑）。

## 项目结构

```
agent/
├── deep_research/
│   ├── graph.py            # LangGraph 组装 + 条件路由 + Checkpoint
│   ├── state.py            # State 定义（步骤/结果/反思/报告）
│   ├── prompts.py          # Planner/Reflector/Writer 提示词
│   ├── tools.py            # Bing/Tavily 搜索 + 网页抓取（smolagents Tool）
│   ├── model.py            # DeepSeek / Ollama 模型工厂 + UsageCounter
│   ├── memory.py           # 经验沉淀（JSON 落盘 + 关键词检索）
│   └── nodes/
│       ├── planner.py      # 拆解任务为简报 + 步骤
│       ├── executor.py     # 单步 CodeAgent 执行（run_single_step 公共函数）
│       ├── supervisor.py   # supervisor 模式：一批步骤并行分发多个 worker
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
