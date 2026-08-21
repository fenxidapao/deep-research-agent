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
| 文档 | ✅ | README + 技术博客（`docs/technical-blog.md`） |
| GitHub | ✅ | `master` 最新 `67ab758`，5 个 commit |

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

## 4. Demo 方案（重点，为"去 demo"准备）

### 4.1 现场 demo 的两条铁律

1. **单任务实测 5-8 分钟**（Bing 搜索 11s/次 × 多轮 × 长报告）——现场不能干等，必须预处理；
2. **必须有降级预案**：网络/API 出问题时不翻车。

### 4.2 三条路线（推荐 A）

- **A. Checkpoint 预演法（推荐）**：现场前用目标任务跑一次，拿到 thread_id 的 checkpoint；现场演示时 `interrupt_before` 在 Writer 前中断，再 `graph.invoke(None)` 续跑——只展示"研究笔记已齐 → 生成报告"的 30 秒，同时讲解前面发生了什么。**需补一个小脚本**（见 4.4）。
- **B. 降参快跑法**：`.env` 临时调低 `MAX_PLAN_STEPS=3`、`MAX_ITERATIONS=2`、`MAX_SEARCHES_PER_STEP=2`，单任务压到 2-3 分钟，现场可完整跑一条简单题（如"全球人口何时破 80 亿"）。
- **C. 预录保底**：先完整录一条任务跑通的视频（含终端输出+最终报告），现场网络出问题直接放视频。

### 4.3 演示选题（按冲击力排序）

1. **时效性题**（展示"它真的会搜最新消息"）：「2026 年 8 月 AI 领域有什么重大发布？」——现场演示，观众看不到的答案最有冲击力；
2. **对比题**（展示 Planner 拆多步 + Reflector 反思）：「对比 langgraph 和 crewAI 的架构差异」；
3. **用户兴趣题**（拉近距离）：「星露谷物语 1.6 新内容」。

### 4.4 建议补的小脚本（30 分钟内）

`demo.py`：输入 task → 后台预跑 → 现场 `interrupt_before=["writer"]` + 续跑，带进度条和节点日志输出（verbosity_level=1），让观众看到 Planner→Executor→Reflector 每步在干什么。

### 4.5 Demo 话术骨架（5 分钟）

```
0:00-0:30  一句话定位：OpenAI Deep Research 的开源可部署版，三节点架构
0:30-1:00  架构图讲解：Planner(拆) → Executor(搜) → Reflector(判) 循环
1:00-4:00  现场跑（路线A/B），边跑边讲每个节点在做什么
4:00-4:30  展示最终报告：结构、来源标注、未查证声明
4:30-5:00  亮数据：16条评测命中率98%、断点恢复7%、成本单任务约0.5元
```

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

## 7. 可选路线图（按价值排序）

1. **Reflector 阈值调优**（修复对照实验暴露的早停问题）：complete 判定要求覆盖关键维度，再跑对照验证命中率提升——这是当前最值得做的改进，也是面试可讲的"迭代故事"；
2. Supervisor 多子 Agent 并行研究（计划书可选）；
3. Chroma 长期记忆（Reflector 沉淀经验）；
4. Docker 部署；
5. Tavily 搜索升级（质量更高，需 key）。

## 8. 一句话总结

项目**主体已 100% 交付**（计划书 4 项交付物全齐，指标真实），剩下的是 demo 打磨（4.2 路线 A + 4.4 小脚本）和可选增强（第 7 节）。
