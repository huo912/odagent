"""FastAPI 可视化后端服务。

提供：
- POST /api/run          上传需求文档（.docx/.txt/.md）或文本，启动生成任务
- GET  /api/status       获取当前进度快照
- GET  /api/events        SSE 实时推送进度
- GET  /api/outputs      列出已生成的文档与工程文件
- GET  /api/outputs/{path} 读取输出文件内容
- GET  /api/project/tree 查看落地工程目录树
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from odagent.crew import ODAgentCrew
from odagent.docx_parser import extract_text
from odagent.checkpoint import get_checkpoint_manager
from odagent.document_writer import ensure_all_documents_on_disk
from odagent.memory import get_memory_store
from odagent.mlflow_tracker import list_runs, log_agent_snapshot
from odagent.project_writer import write_project
from odagent.tracker import get_tracker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"
GENERATED_DIR = OUTPUT_DIR / "generated_project"

app = FastAPI(title="OmniDev Agent 可视化服务")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tracker = get_tracker()

# 运行锁，避免并发启动多个任务
_run_lock = threading.Lock()
_running = False


def _safe_name(filename: str) -> str:
    return Path(filename).name


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def status():
    return tracker.snapshot()


@app.post("/api/pause")
def pause_agent(name: str = Form(...)):
    """暂停指定 Agent（在下一步执行前阻塞）。"""
    tracker.pause_agent(name)
    return {"name": name, "paused": True}


@app.post("/api/resume")
def resume_agent(name: str = Form(...)):
    """继续指定 Agent。"""
    tracker.resume_agent(name)
    return {"name": name, "paused": False}


@app.get("/api/events")
async def events():
    """SSE 实时推送进度。"""
    queue: asyncio.Queue = asyncio.Queue()

    def listener(snapshot: dict):
        try:
            queue.put_nowait(snapshot)
        except Exception:
            pass

    tracker.add_listener(listener)

    async def gen():
        try:
            # 先推送当前快照
            yield f"data: {json.dumps(tracker.snapshot(), ensure_ascii=False)}\n\n"
            while True:
                try:
                    snapshot = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 心跳，保持连接
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _record_mlflow(requirement: str, run_id: str) -> None:
    """将本次运行中每个 Agent 的快照记录到 MLflow。"""
    try:
        snapshot = tracker.snapshot()
        for agent in snapshot.get("agents", []):
            log_agent_snapshot(
                run_id=run_id,
                agent_name=agent.get("name", ""),
                role=agent.get("role", ""),
                snapshot=agent,
                requirement=requirement,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"MLflow 记录失败: {exc}")


def _run_crew(
    requirement: str,
    run_id: str,
    selected_agents: list[str] | None = None,
    resume: bool = False,
) -> None:
    """在后台线程中执行 Crew 并落地工程。"""
    global _running
    try:
        tracker.start_run(run_id, requirement[:200])
        ODAgentCrew(tracker=tracker, run_id=run_id, resume=resume).kickoff(
            inputs={"requirement": requirement},
            selected_agents=selected_agents,
        )
        tracker.finish_run(success=True)

        # 将每个 Agent 的执行指标记录到 MLflow
        _record_mlflow(requirement, run_id)

        # 文档落盘保障：确保所有 Agent 的文档正文真正写到磁盘
        # （Agent 可能把正文存到记忆而只输出过程确认，这里做兜底重组）
        landed = ensure_all_documents_on_disk()
        print(f"文档落盘保障完成: {landed}")

        # 工程落地：全栈代码 + 测试代码
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        fullstack_md = OUTPUT_DIR / "fullstack_code.md"
        test_md = OUTPUT_DIR / "software_test_plan.md"
        if fullstack_md.exists():
            stats = write_project(
                fullstack_md.read_text(encoding="utf-8"), GENERATED_DIR
            )
            print(f"全栈代码落地完成: {stats}")
        if test_md.exists():
            stats = write_project(
                test_md.read_text(encoding="utf-8"), GENERATED_DIR
            )
            print(f"测试代码落地完成: {stats}")
        tracker.snapshot()  # 触发广播
    except Exception as exc:  # noqa: BLE001
        tracker.finish_run(success=False)
        print(f"任务失败: {exc}")
    finally:
        _running = False


@app.post("/api/run")
async def run_task(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    agents: str = Form(default=""),
    resume: str = Form(default=""),
):
    global _running
    if _running:
        raise HTTPException(status_code=409, detail="已有任务正在运行，请稍候")

    # 解析输入
    if file is not None:
        filename = _safe_name(file.filename or "")
        suffix = Path(filename).suffix.lower()
        if suffix not in (".docx", ".txt", ".md", ".markdown"):
            raise HTTPException(status_code=400, detail="仅支持 .docx / .txt / .md 文件")
        content = await file.read()
        tmp = OUTPUT_DIR / f"_upload_{uuid.uuid4().hex[:8]}{suffix}"
        tmp.write_bytes(content)
        try:
            requirement = extract_text(tmp)
        finally:
            tmp.unlink(missing_ok=True)
    elif text.strip():
        requirement = text.strip()
    else:
        raise HTTPException(status_code=400, detail="请上传需求文档或输入需求文本")

    # 解析选中的 agent（逗号分隔的 key 列表；为空则执行全部）
    selected_agents: list[str] | None = None
    if agents.strip():
        selected_agents = [a.strip() for a in agents.split(",") if a.strip()]

    # 检查点恢复：resume 为 true 时，从指定 run_id 恢复（跳过已完成任务）
    resume_flag = resume.strip().lower() in ("1", "true", "yes", "on")
    run_id = uuid.uuid4().hex[:8]
    _running = True
    thread = threading.Thread(
        target=_run_crew,
        args=(requirement, run_id, selected_agents, resume_flag),
        daemon=True,
    )
    thread.start()
    return {"run_id": run_id, "message": "任务已启动"}


@app.get("/api/mlflow/runs")
def mlflow_runs(limit: int = 50):
    """返回 MLflow 中记录的 Agent 执行指标，供前端可视化面板使用。"""
    try:
        return {"runs": list_runs(limit=limit)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取 MLflow 数据失败: {exc}")


# ---- 记忆系统 API ----
@app.get("/api/memory")
def list_memories(agent: str = ""):
    """列出指定 Agent（或全部）的记忆。"""
    store = get_memory_store()
    if agent:
        return {"memories": store.all(agent)}
    result = {}
    for key in (
        "requirements_analyst",
        "software_architect",
        "database_analyst",
        "senior_fullstack_engineer",
        "senior_software_test_engineer",
    ):
        result[key] = store.all(key)
    return {"memories": result}


@app.post("/api/memory")
async def save_memory(
    agent: str = Form(...),
    key: str = Form(...),
    content: str = Form(...),
):
    """手动保存一条记忆。"""
    get_memory_store().save(agent, key, content)
    return {"agent": agent, "key": key, "saved": True}


@app.delete("/api/memory")
def delete_memory(agent: str = "", key: str = ""):
    """删除指定记忆；agent 为空时清空全部。"""
    store = get_memory_store()
    if agent and key:
        store.delete(agent, key)
    elif agent:
        store.clear(agent)
    else:
        for k in (
            "requirements_analyst",
            "software_architect",
            "database_analyst",
            "senior_fullstack_engineer",
            "senior_software_test_engineer",
        ):
            store.clear(k)
    return {"cleared": True}


# ---- 检查点 API ----
@app.get("/api/checkpoints")
def list_checkpoints(limit: int = 20):
    """列出最近的检查点。"""
    return {"checkpoints": get_checkpoint_manager().list_checkpoints(limit=limit)}


@app.get("/api/checkpoints/{run_id}")
def get_checkpoint(run_id: str):
    """获取指定 run_id 的检查点详情。"""
    return get_checkpoint_manager().get(run_id)


@app.delete("/api/checkpoints/{run_id}")
def delete_checkpoint(run_id: str):
    """删除指定检查点。"""
    get_checkpoint_manager().clear(run_id)
    return {"cleared": True}


@app.get("/api/outputs")
def list_outputs():
    """列出 output 目录下的文档。"""
    files = []
    if OUTPUT_DIR.exists():
        for p in sorted(OUTPUT_DIR.glob("*.md")):
            files.append(
                {
                    "name": p.name,
                    "size": p.stat().st_size,
                    "path": p.name,
                }
            )
    return {"files": files}


@app.get("/api/outputs/{name}")
def read_output(name: str):
    safe = _safe_name(name)
    p = OUTPUT_DIR / safe
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(p, media_type="text/markdown; charset=utf-8")


@app.get("/api/project/tree")
def project_tree():
    """返回落地工程目录树。"""
    if not GENERATED_DIR.exists():
        return {"tree": [], "root": str(GENERATED_DIR)}
    tree = _build_tree(GENERATED_DIR)
    return {"tree": tree, "root": str(GENERATED_DIR)}


def _build_tree(path: Path, prefix: str = "") -> list[dict]:
    items = []
    for child in sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name)):
        if child.name.startswith("."):
            continue
        node = {"name": child.name, "type": "file" if child.is_file() else "dir"}
        if child.is_dir():
            node["children"] = _build_tree(child)
        items.append(node)
    return items


@app.get("/api/project/file")
def read_project_file(path: str = ""):
    """读取落地工程中的文件内容。"""
    if not path:
        raise HTTPException(status_code=400, detail="缺少 path 参数")
    safe = path.replace("\\", "/").lstrip("/")
    parts = [p for p in safe.split("/") if p not in ("", ".", "..")]
    target = GENERATED_DIR.joinpath(*parts)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target)


def main() -> None:
    """启动可视化服务。"""
    import uvicorn

    host = "0.0.0.0"
    port = 8000
    print(f"OmniDev Agent 可视化服务已启动: http://{host}:{port}")
    print(f"前端页面: http://{host}:{port}/  （需先构建 web 前端）")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
