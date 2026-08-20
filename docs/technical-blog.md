# 从零构建一个「规划-执行-反思」三节点深度研究 Agent

> LangGraph + smolagents 落地实录：架构、踩坑与量化评测

## 背景

深度研究（Deep Research）是 2024 年以来最受关注的 Agent 应用形态：输入一个问题，Agent 自动规划子问题、多轮搜索、反思信息充分性，最终产出一份带引用来源的结构化报告。

参考业界已有项目（LangChain 的 open_deep_research、OpenAI 的 deep research），我们决定自研一个三节点版本，目标：
1. **编排层**用 LangGraph 显式实现 Planner / Executor / Reflector 三节点 + 条件边回环；
2. **执行层**用 smolagents 的 CodeAgent 作为工具调用内核（代码执行式，比纯工具调用更灵活）；
3. **国内可用**：搜索走 Bing 国内版，模型走 DeepSeek API，全程无需科学上网。

## 架构

```
Planner ──▶ Executor ──▶ Reflector ──┬─ continue → Executor
    ▲                                 ├─ replan   → Planner（带已有进展）
    └─────────────────────────────────┴─ complete → Writer → END
```

- **Planner**：把用户任务改写为"调研简报"（research_brief），再拆解为 3~6 个有序步骤，每步带建议搜索关键词。输出严格 JSON。
- **Executor**：取当前步骤，构造 smolagents CodeAgent（挂载 web_search / fetch_page 两个工具），Agent 自己写 Python 代码完成"搜索→抓取→提炼"循环，产出研究笔记。
- **Reflector**：读取调研简报 + 已完成笔记 + 剩余步骤，判定 continue / replan / complete。带硬性预算护栏（最大轮数、步骤耗尽即强制收尾）。
- **Writer**：汇总全部研究笔记，生成 Markdown 报告。

共享 State：`task / research_brief / plan / completed_steps / intermediate_results / search_history / reflection / iteration / status / final_report`。

## 关键实现

### 1. Executor 为什么用 smolagents CodeAgent

smolagents 的核心思路是"让模型写代码、代码调工具"，而不是"模型逐个调工具"（ReAct）。区别在于：

- ReAct：模型每一步输出一个 tool call，LLM 决定全部控制流，token 消耗大、易死循环；
- CodeAgent：模型写一段 Python 代码，工具调用只是函数调用，循环/分支由代码控制，更接近"人用工具"的方式。

实测对"多轮搜索 + 提炼事实"这类任务，CodeAgent 的轨迹更紧凑。

### 2. 国内环境的搜索选型（踩坑实录）

这是本项目的最大坑。最初按惯性选了 `duckduckgo-search`，结果：

1. 包已改名 `ddgs`，旧 API 不兼容；
2. 更致命的是 **DuckDuckGo 全部后端在国内不可达**（api.duckduckgo.com 超时、html 端点超时、Bing 后端被反爬返回空）。

逐一实测后可行的方案：
- **cn.bing.com 直连可用**（约 11s/请求），用 lxml XPath 解析 `li.b_algo` 提取标题/链接/摘要——免费、无需 key；
- **Tavily**（需 key，质量更高）作为可选升级；
- 百度 302 重定向 + 反爬，放弃。

最终默认 `bing`，支持 `tavily` 切换。

### 3. f-string 与 str.format 的双重转义

写提示词时用了 f-string 模板，模板里又有 `.format()` 占位符和 JSON 示例（含花括号），导致 `{{` 被 f-string 先转义成 `{`，随后 `.format()` 又把 JSON 示例误认为占位符，直接 `KeyError`。

教训：**提示词模板统一用普通字符串 + `.format()`**，JSON 示例的花括号用 `{{}}` 转义，一处转义、一处渲染，不要混用 f-string。

### 4. smolagents 版本 API 变化

`OpenAICompatibleModel` 在 1.26 版本被拆分为 `OpenAIModel`（OpenAI 兼容 API 客户端）与 `OpenAIServerModel`。开发时以 `dir(models)` 实际检查为准，别依赖记忆。

## 评测方法

评测集 16 条，分两类：
- **多源综合题**（对比、综述）：需要多步搜索 + 综合，体现三节点价值；
- **事实核查题**：单步可答，测效率。

每条带 `must_contain` 关键词列表，报告命中即得分，全自动打分，指标：
- 规划成功率、报告完成率、答案命中率
- 平均执行步骤 / 循环轮数 / 耗时
- 断点恢复耗时（Checkpoint 价值）

## 结果

（评测跑完补充）

## 总结

- 三节点架构的价值在 **Reflector 的 replan 分支**：当搜索结果暴露原计划漏洞时能回头修正，这是"能跑"和"会做事"的分水岭；
- 国内 Agent 项目绕不开的三个问题：模型（DeepSeek 性价比最优）、搜索（Bing 免费兜底 / Tavily 升级）、网络（一切以实测为准）；
- 提示词模板的转义、框架 API 变化这类"小坑"最耗时间，建议锁定版本。
