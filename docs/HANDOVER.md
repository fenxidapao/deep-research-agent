# Deep Research Agent — 交接文档（HANDOVER）

> 给新窗口/协作者的完整接手说明。核心目标：**快速跑通 demo + 扩展**。
> 项目仓库：https://github.com/fenxidapao/deep-research-agent

---

## 1. 项目是什么（30 秒版）

LangGraph 编排 + smolagents 内核的「规划-执行-反思」三节点深度研究 Agent：
输入一个问题 → Planner 拆解调研简报+步骤 → Executor（smolagents CodeAgent）多轮搜索/抓网页 → Reflector 判定 继续/重规划/收尾 → Writer 输出带来源的 Markdown 报告。

## 2. 当前状态快照（已完成）

| 交付物 | 状态 | 关键数据 |
|---|---|---|
| 三节点架构代码 | ✅ 完整 | `deep_research/` 包 |
| CLI + FastAPI | ✅ 可用 | `main.py` / `api.py` |
| 量化评测 | ✅ 完成 | 16 条：规划成功率 100%、报告完成率 100%、命中率 98%、平均 7.1min/条 |
| 断点恢复 | ✅ 完成 | 恢复仅 18.4s（占全流程 7%） |
| 反思对照实验 | ✅ 完成 | 3 条小样本：反思省 ~30% token/耗时，命中率 -0.11（早停漏词） |
| pytest 测试 | ✅ 完成（8/21） | 53 用例全 mock，1s 跑完，不依赖 API/网络 |
| logging 化 | ✅ 完成（8/21） | 节点进出/模型调用/异常结构化日志（`logging_utils.py`） |
| 经验沉淀 | ✅ 完成（8/21） | 失败→落盘→Planner 注入（`memory.py`，53 用例含闭环） |
| supervisor 多 Agent | ✅ 完成（8/21） | 一批步骤并行分发 worker（`supervisor.py`，CLI `--supervisor`） |
| 文档 | ✅ | README（含生产化设计章节）+ 技术博客 + 交接文档 |
| GitHub | ✅ | `master` 最新 `ee3393c`，9 个 commit |

## 3. 运行指南（三分钟跑起来）

```bash
cd "E:\AI 应用开发\agent"
.venv/Scripts/python.exe main.py "2024年巴黎奥运会中国金牌数"   # CLI
.venv/Scripts/python.exe evaluate.py --limit 2                 # 快速评测（断点续跑）
.venv/Scripts/python.exe -m uvicorn api:app --port 8000        # FastAPI
.venv/Scripts/python.exe ablation.py --id 1 --id 3             # 反思对照实验
```

**环境**：Python venv 在 `.venv/`（Python 3.13），依赖在 `requirements.txt` 已装好。
**配置**：`.env`（勿提交，已 gitignore）含 DeepSeek API key；模型 `deepseek-v4-flash`（便宜），搜索默认 `bing`（免费直连）。

## 4. 「完整落地项目」改造清单（项目用于简历，目标是去 demo 感）

> 面试官区分"demo 玩具"和"落地项目"不看它跑得多顺，而看：**有测试吗？有评测吗？有容错吗？有工程结构吗？有迭代证据吗？**

### 4.1 现状盘点：已具备的落地特征（面试可讲的硬证据）

| 维度 | 现状 | 证据 |
|---|---|---|
| 工程结构 | ✅ 包化 + CLI + API + 配置分离 | `deep_research/` 包、`main.py`、`api.py`、`.env` |
| 量化评测 | ✅ 16 条自动打分 + 4 项指标 | 命中率 98%、断点恢复 7%、成本/条约 0.5 元 |
| 容错 | ✅ 重试/兜底/预算护栏 | Writer 三重试、Planner 解析兜底、max_steps/轮数硬上限 |
| 文档 | ✅ README + 技术博客 + 交接文档 | 含架构图、踩坑记录、成本记录 |
| 版本管理 | ✅ Git 6 个 commit 记录真实迭代 | 从架构→评测→修复→指标补全 |
| 研究证据 | ✅ 对照实验（含反面结果） | ablation 暴露"早停伤准确率"，是迭代故事的素材 |
| 成本意识 | ✅ 全项目 5~6 元跑完 | 简历/面试可直接讲 |

### 4.2 缺口清单（按优先级，决定"落地感"的强度）

1. ~~**pytest 单元/集成测试（最高优先，约 1-2 小时）**~~ ✅ 已完成（8/21，39 用例全绿）
   - 必测：`_extract_json` 的容错、`UsageCounter` 计数、Bing 解析（mock 响应）、`_route` 三路由、Writer 空输出重试逻辑；
   - 加分：一条 mock 搜索的端到端集成测试（不调真实 API）✅ 已含（含 replan 循环路由）；
   - 面试问答"如何保证质量"时，测试文件就是答案。
2. ~~**README 增加「生产化设计」章节（30 分钟）**~~ ✅ 已完成（8/21）——把隐性设计显性化：预算护栏、断点续跑、容错策略、成本控制、搜索降级（Bing→Tavily→Ollama 离线）。
3. ~~**logging 替换 print（约 1 小时）**~~ ✅ 已完成（8/21）——节点进出、模型调用、异常记录结构化日志；CLI 日志走 stderr 保证 `--json` stdout 纯净。
4. **Docker 部署（可选，约 1 小时）**——"可部署"是落地项目的标志；`Dockerfile` + `docker-compose`（API 服务）。未做，按需。
5. **不要做**：现场演示脚本、话术、预录视频——这些是 demo 思维，与目标相反。

### 4.3 简历/面试叙事建议（比代码更重要的"去 demo 感"手段）

- **讲"问题→方案→量化→迭代"**，不讲"我用了 LangGraph"：方案是三节点为什么这么拆、Reflector 的重规划价值是什么；
- **主动讲数据**：16 条评测集怎么设计的、98% 命中率怎么测的、断点恢复 7% 意味着什么、全项目成本 5~6 元；
- **主动讲反面发现**：ablation 显示反思省 30% 成本但早停伤准确率——比"我的系统完美"更可信，顺势讲"下一步调优 Reflector 阈值"；
- **主动讲踩坑**：API 偶发空输出、搜索被墙、框架 API 变更——证明是真实做出来的；
- **一句话定位模板**：「一个可部署的深度研究 Agent：LangGraph 编排三节点循环，smolagents 执行，16 条评测命中率 98%，断点恢复成本 7%，全项目 API 成本 5 元。」

### 4.4 行动进度（8/21 已执行完毕）

- [x] 写 `tests/`（39 用例全 mock，全绿，约 1s）
- [x] README 补「生产化设计」章节
- [x] logging 化（节点/入口结构化日志）
- [ ] （可选）Docker 部署
- [x] 提交推送定稿（`ee3393c`，9 commits）

剩余可选扩展见第 8 节（Reflector 阈值调优 / CourseRAG 集成 / Memory 沉淀 / supervisor）。

## 5. 关键技术备忘（踩坑清单，新窗口别再踩）

1. **smolagents 1.26**：`OpenAICompatibleModel` 已拆成 `OpenAIModel`；CodeAgent 无 `max_execution_time` 参数，超时经 `executor_kwargs={"timeout_seconds": 180}`；Agent 内部走 `model.generate()` 非 `__call__`，token 包装要双入口。
2. **LangGraph 1.2**：`interrupt_before` 是 invoke 的**关键字参数**（`graph.invoke(input, interrupt_before=[...])`），不是 config 键，放错位置静默失效。
3. **搜索**：DuckDuckGo 国内不可达（含改名后的 `ddgs` 包）；Bing 国内版（cn.bing.com）可直连但慢（~11s/次），解析用 lxml XPath（`li.b_algo`），百度反爬 302。
4. **提示词**：勿用 f-string + `.format()` 混用（双重转义冲突）；JSON 示例花括号用 `{{}}`。
5. **DeepSeek**：账号模型是 `deepseek-v4-flash`/`deepseek-v4-pro`（不是默认 deepseek-chat）；API 偶发返回空 content → Writer 已加三重试+兜底；余额不足会 402。
6. **评测可靠性**：进度实时落盘（`progress.jsonl`）断点续跑；命中匹配大小写不敏感；`ablation.py` 独立脚本逐条落盘。
7. **本机环境坑**：WorkBuddy 后台 bash 任务的 tasklist 监控不可靠（进程"看似消失"实际在跑），判断完成**以落盘文件为准**；长任务建议前台跑或逐条落盘。

## 6. 成本记录（用户实测）

| 项目 | 花费 |
|---|---|
| 全量 16 条评测 + demo + 调试 | 约 5~6 元 |
| 反思对照 3 条 | 约 1~1.5 元 |
| 断点恢复测试单次 | 约 0.3 元 |

## 7. 扩展取舍判断（对照生产级 9 步流程 + RAG 集成可行性）

> 用户提供了一份「AI Agent 搭建全流程」9 步清单（定义/Context/Tools/Workflow/Memory/Harness/Evaluation/Loop/Multi-Agent）。
> 定性：**生产级工程全景清单——价值在面试讲认知，不在逐条落地**。"什么都做但都是皮毛"不如"核心做深 + 讲清全景"。

### 7.1 值得做（性价比排序）

| 项 | 原因 | 工作量 | 状态 |
|---|---|---|---|
| pytest 测试 | 工程化最硬证据，面试答"怎么保证质量" | 1-2h | ✅ 8/21 完成（60 用例） |
| Memory 经验沉淀 | Agent 面试高频题"怎么记忆"；把反思/搜索失败经验写 JSON 下次读取 | 1-2h | ✅ 8/21 完成（`deep_research/memory.py`，失败→落盘→Planner 注入） |
| 浅层 Multi-Agent | supervisor-worker 是高频面试题，照 langgraph-supervisor 做任务分发即可 | 2-4h | ✅ 8/21 完成（`supervisor.py`，不引依赖自研，worker 复用 run_single_step） |
| logging | 代码观感，面试官翻代码看得出 | 1h | ✅ 8/21 完成（`logging_utils.py`） |

### 7.2 不值得做（面试官/简历视角 + 理由）

| 项 | 为什么不做 |
|---|---|
| 工具权限审批/人工确认 | 无真实敏感场景，为做而做；面试官一问"审批什么"就露馅 |
| Loop 定时触发/任务调度 | 运维场景，简历展示不出价值，追问"调度失败怎么办"进坑 |
| 人工修改率/用户满意度 | 无真实用户，无法产生数据，硬写是必被戳穿的破绽 |
| 深度 Multi-Agent（消息队列/服务发现/负载均衡） | 分布式系统范畴，做不动讲不清，深挖即露怯 |
| 硬加 RAG | 与搜索能力重叠，除非有现成资产与场景（见 7.3） |
| Workflow 模板 | 单一用途研究 agent 意义不大 |

### 7.3 CourseRAG 集成可行性（已有现成资产，结论：值得，走最小集成）

**现状**（E:\WorkBuddy工作空间\2026-08-16-17-06-49\CourseRAG，8/16-8/20 迭代）：
- 技术栈：Ollama nomic-embed-text（本地 embedding）+ chromadb + **混合检索（向量+自研 BM25+RRF）** + 可选 bge-reranker-v2-m3 两段式重排
- 数据：12 份课程文档（数据结构/组成原理/操作系统/数据库/计网），支持 md/pdf/docx
- **自带 FastAPI 服务**（main.py）：`POST /retrieve`（仅检索+重排，不生成——集成正用这个端点）、`/query`、文档管理、索引重建、`/health`
- 自带四指标自评测（faithfulness/answer_relevancy/context_precision/context_recall）

**集成方案（推荐 HTTP 解耦，零侵入）**：
1. RAG 起服务：`uvicorn main:app --port 8001`（需本机 Ollama 运行，embedding 依赖它）
2. Agent 侧新增 `course_retrieve` 工具（smolagents Tool，requests POST /retrieve），挂到 Executor 的 CodeAgent
3. 提示词告知 CodeAgent：研究题目涉及课程内容时优先查本地库
4. 工作量：0.5-1.5h；风险：Ollama 服务必须起（demo/评测多一个依赖）

**面试价值**：这是"RAG + Agent"组合故事——两个独立项目整合成"研究 Agent 的私有知识库工具"，且 RAG 的混合检索/reranker/四指标评测全是经典面试考点，用户有真实实现与数据。
**注意**：别让 RAG 喧宾夺主，Agent 是主角、RAG 是工具之一；评测可加 2-3 条课程题对比"纯 web 搜索 vs web+RAG"命中率，作为组合价值的量化证明。

## 8. 可选路线图（按价值排序）

1. ~~**pytest 测试**~~ ✅ 8/21 完成（53 用例全绿）；
2. **Reflector 阈值调优**（修复对照实验暴露的早停问题：complete 判定要求覆盖关键维度）——面试可讲的"迭代故事"；
3. **CourseRAG 集成**（7.3，现成资产，0.5-1.5h）；
4. ~~**Memory 经验沉淀**~~ ✅ 8/21 完成（`memory.py`，失败→落盘→Planner 注入）；
5. ~~**浅层 Multi-Agent supervisor**~~ ✅ 8/21 完成（`supervisor.py`，CLI `--supervisor`）；
6. Docker 部署；
7. Tavily 搜索升级（质量更高，需 key）。

> 另有已知遗留项（未修）：Planner 重规划将 `iteration` 重置为 0，`max_iterations` 护栏在 replan 循环下失效——与路线图 2 一并处理。

## 9. 一句话总结

项目**已按"完整落地"标准定稿**（8/21）：39 个 pytest 全绿 + README 生产化设计 + logging 化，commit `ee3393c` 已推送。剩余均为可选：Docker 部署、Reflector 阈值调优（修早停）、CourseRAG 集成。**已知遗留项**：Planner 重规划将 `iteration` 重置为 0，`max_iterations` 护栏在 replan 循环下失效（步骤/搜索仍受兜底，不会失控），详见 README「生产化设计」。
