# smolagents 开源 PR 行动指南（2026-08-22 选点）

> 目标：1~2 个真实可合并的 PR,给简历加"外部认可"证据。
> 原则：**核心代码自己写**,AI 只做选点、读代码辅助、审阅。
> 时间盒：2~3 周,到点没合并就止损(它是加分项,不是主线)。

---

## 1. 选点结论(已实测验证)

### 候选 A(推荐首做):补 CodeAgent 超时参数文档

**为什么值得做**:
- 你踩过的坑(HANDOVER 第 1 条):"CodeAgent 无 max_execution_time 参数,超时经 executor_kwargs={'timeout_seconds': 180}"。
- **实测:官方 docs/ 目录 grep `timeout_seconds` / `executor_kwargs` 零结果**——文档确实缺失,这是真实用户痛点,不是臆造。
- 相关 issue #1129("Is there a step timeout feature?")存在已久,说明社区确实困惑。

**具体动作**:
1. fork `huggingface/smolagents`,本地 clone;
2. 在 `docs/source/en/` 找到 CodeAgent/agents 相关文档页(如 `docs/source/en/tutorials/secure_code_execution.md` 或 agents 指南),补一节"代码执行超时":
   - 说明默认 `MAX_EXECUTION_TIME_SECONDS = 30`(src/smolagents/local_python_executor.py:60);
   - 说明如何覆盖:CodeAgent(executor_kwargs={"timeout_seconds": 180});
   - 给出一个真实示例(如你的 180s 配置);
3. 最小改动 + 英文文档,提 PR 时引用 issue #1129 说明"社区长期困惑,文档未覆盖"。

**合并概率**:高(纯文档,无 API 变更风险)。**含金量**:中等,但它是第一个 PR 的稳妥起点,能建立贡献记录。

### 候选 B(进阶,等 A 合并后):跟进 #2378 冲突

**现状(实测)**:PR #2378 想给 CodeAgent 加 `max_execution_time_seconds` 一等参数,但 2026-06-14 创建后**零审查零合并**,且其描述称"30 秒超时硬编码"——**与当前 main 不符**(main 已支持 executor_kwargs 覆盖),说明它基于旧代码,已过时冲突。

**为什么值得做**:
- 痛点真实(issue #1129 长期 open);
- 现有一等参数设计有缺陷(藏在 executor_kwargs 里不易发现,文档也没写)——改进为显式参数是合理演进;
- 若能帮 #2378 作者或重新实现,是"解决他人遗留问题"的强叙事。

**风险**:维护者可能因 #2378 已存在而不收新 PR,或对 API 设计有自己想法。**建议**:先评论 #2378 询问状态(礼貌、专业),再决定是自己重新实现还是等合并。

### 候选 C(备选):修 `validate_tool_attributes` 的 keyword-only 校验缺陷

**现状(实测)**:issue #2668([BUG] validate_tool_attributes never checks keyword-only...)+ PR #2672(fix)刚出现,是活跃热点。**注意**:已有 PR #2672 在修,别撞车,除非 #2672 失败被关。

---

## 2. 已排除的候选(别浪费时间)

| 候选 | 排除理由 |
|---|---|
| chroma-core/chroma | good-first-issue 是 2024 年老 issue,且 Rust+Python 混合大项目,PR 周期不可控 |
| langgraph | 4 万 star 超大项目,维护者少,新人 PR 很难被看到 |
| tavily-python | 1.4k star 太小,无含金量 |
| typo/文档错别字 PR | 面试官一眼看穿是刷 PR,扣分 |

## 3. 操作清单(你的待办)

1. [ ] fork smolagents → 本地 clone(已浅克隆参考在 E:\AI 应用开发\smolagents-dev,可复用)
2. [ ] 读 docs/source/en/ 现有 agents 文档结构,确定插入位置
3. [ ] 写超时文档小节(英文,含示例),引用 #1129
4. [ ] 本地跑文档构建或至少 py_compile 相关改动,提交 PR
5. [ ] PR 描述:说明文档缺口 + 关联 issue + 附上"真实用户因缺文档踩坑"的论据
6. [ ] 合并后(或并行),评论 #2378 问状态,评估候选 B
7. [ ] 时间盒 2~3 周,到点没动静 → 止损,把 PR 链接写进简历即可(即使未合并,提了有价值的 PR 也是叙事素材,但要如实说状态)

## 4. 面试怎么讲(无论合并与否)

- 合并了:「给 smolagents 提交过文档 PR 修复社区长期困惑的超时配置问题,被维护者合并」——**有链接可查**;
- 未合并:「给 smolagents 提过 PR 解决 X,目前维护者还在 review」——**如实,不吹**;继续迭代 PR 本身也是故事。
