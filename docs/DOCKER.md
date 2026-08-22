# Docker 部署方案（Deep Research Agent API）

> 目标：把 FastAPI 服务容器化，一条命令起服务，可迁移、可编排。
> 状态：方案已定稿（2026-08-22），文件已就绪，**本机未装 Docker 未实测**（验证命令见 §6）。

## 1. 架构决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 基础镜像 | `python:3.13-slim` 单阶段 | 依赖（langgraph/smolagents/litellm/lxml）全有 wheel，无 C 编译；单阶段即可，避免过度设计。若未来引入需编译的依赖，再拆多阶段（builder 编译 + runtime 只拷产物） |
| 密钥管理 | **不进镜像**，compose `env_file: .env` 注入 | 镜像层可被 `docker history` 反查，密钥写入即泄漏 |
| 经验沉淀持久化 | `memory/` 挂载命名卷 | `ExperienceMemory` 是 L1 自进化资产，容器重建不丢 |
| Checkpoint | MemorySaver（内存）→ **重启丢失** | 当前实现如此；生产化增强项：`langgraph-checkpoint-sqlite` 的 `SqliteSaver` 落盘 |
| 健康检查 | `GET /health`（api.py 已实现）| 编排/负载均衡依赖 |
| 运行用户 | 非 root `appuser` | 容器安全最佳实践（纵深防御） |
| 端口 | 8000（可改）| 与 uvicorn 默认一致 |

## 2. 文件清单

- `Dockerfile`：构建（依赖层缓存 + 代码 + 非 root + 健康检查）
- `.dockerignore`：排除 `.venv/.env/eval_set/.git/memory/tests/.workbuddy` 等（构建上下文瘦身 + 防密钥误入）
- `docker-compose.yml`：服务编排（端口/环境变量/卷/健康检查/自动重启）
- 本文档

## 3. 构建与运行

```bash
# 构建
docker build -t deep-research-agent:latest .

# 运行（需 .env 含 DEEPSEEK_API_KEY）
docker compose up -d
curl http://localhost:8000/health          # → {"status":"ok",...}
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"task": "2026 年 AI 行业十大趋势"}'
```

## 4. 配置说明（compose 环境变量）

- `env_file: .env` 直接复用本地配置（DEEPSEEK_API_KEY / SEARCH_PROVIDER 等，见 `deep_research/config.py`）
- 额外环境变量可覆盖：`MODEL_PROVIDER=ollama` 可接本地 Ollama（需 `network_mode: host` 或指向宿主机 IP，Windows/Mac 下 Docker 访问宿主机用 `host.docker.internal`）
- API 当前固定单步模式（`build_graph(cfg)`），supervisor 并行模式未暴露到 API——增强项可加 `SUPERVISOR_ENABLED` 环境变量

## 5. 生产注意事项（面试/上生产前必读）

1. **重启丢 Checkpoint**：MemorySaver 在容器重启后丢失断点状态，长任务中断无法续跑。生产方案：`SqliteSaver`（挂载卷）。
2. **网络出站**：容器需访问 `api.deepseek.com` + `cn.bing.com`。企业内网/受限网络需配代理（`HTTP_PROXY/HTTPS_PROXY` 环境变量）。
3. **并发**：单 worker uvicorn 下 `/run` 是同步阻塞的（一次一个任务）。生产可按需 `--workers N`，但注意 token 计数/经验文件并发写（已加锁，安全）。
4. **日志**：容器 stdout/stderr 由 Docker 收集（`docker logs`），项目 logging 已结构化，可直接接 ELK/Loki。
5. **安全**：镜像不含 .env；`/run` 无鉴权——生产须前置网关/API Key。

## 6. 验证清单（2026-08-22 已实测通过 ✅）

```bash
docker build -t deep-research-agent:latest .   # ✅ 通过（加速器 docker.xuanyuan.me）
docker compose config                           # ✅ 语法通过
docker compose up -d && docker compose ps       # ✅ 容器 Up (healthy)
curl -s http://localhost:8000/health            # ✅ {"status":"ok","provider":"deepseek","search":"bing"}
curl -s -X POST http://localhost:8000/run -H "Content-Type: application/json" -d '{"task":"Python 3.13 新特性"}' | head -c 200
# ✅ status=complete，178.7s 出报告（容器内 DeepSeek+Bing 出站正常）
docker compose down                             # 停止（卷保留）；restart: unless-stopped 已设
```

> 国内网络注意：Docker Hub 直连超时，已配 `registry-mirrors`（docker.xuanyuan.me / docker.1ms.run / dockerproxy.net）。数据目录建议迁 E 盘：Settings → Resources → Advanced → Disk image location。
