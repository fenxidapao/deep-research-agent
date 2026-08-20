"""FastAPI 接口：POST /run 运行研究任务，GET /health 健康检查。

启动：uvicorn api:app --port 8000
"""

import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from deep_research import build_graph, get_config

app = FastAPI(title="Deep Research Agent API", version="0.1.0")

cfg = get_config()
graph = build_graph(cfg)


class RunRequest(BaseModel):
    task: str
    thread_id: str | None = None  # 传相同 thread_id 可断点续跑


class RunResponse(BaseModel):
    task: str
    final_report: str
    research_brief: str
    plan: list
    completed_steps: list
    iteration: int
    status: str
    thread_id: str
    elapsed_seconds: float


@app.get("/health")
def health():
    return {"status": "ok", "provider": cfg.provider, "search": cfg.search_provider}


@app.post("/run", response_model=RunResponse)
def run_task(req: RunRequest):
    thread_id = req.thread_id or f"api-{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    final = graph.invoke(
        {"task": req.task},
        config={"configurable": {"thread_id": thread_id}},
    )
    return RunResponse(
        task=req.task,
        final_report=final.get("final_report", ""),
        research_brief=final.get("research_brief", ""),
        plan=final.get("plan", []),
        completed_steps=final.get("completed_steps", []),
        iteration=final.get("iteration", 0),
        status=final.get("status", ""),
        thread_id=thread_id,
        elapsed_seconds=round(time.time() - t0, 1),
    )
