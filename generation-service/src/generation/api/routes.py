import json
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import TaskOutput
from ..services.model_service import model_service, seed_models
from ..services.task_service import redis_client, task_service

router = APIRouter()


def user_id(request: Request) -> int | None:
    raw = request.headers.get("X-User-Id")
    return int(raw) if raw else None


@router.get("/api/v1/models")
def list_models(request: Request, type: str | None = None, db: Session = Depends(get_db)):
    return {"items": model_service.list_models(db, type, include_disabled=False)}


@router.post("/api/v1/models/estimate")
def estimate(body: dict, db: Session = Depends(get_db)):
    model_type = body.get("modelType", "text")
    params = body.get("modelParams") or {}
    count = int(body.get("count", 1))
    result = task_service.estimate(db, model_type, params, count)
    if not result.get("models"):
        raise HTTPException(status_code=404, detail="该类型暂无可用模型")
    cheapest = min(result["models"], key=lambda m: m["estimatedCost"])
    return {"estimatedCost": cheapest["estimatedCost"], "models": result["models"]}


@router.get("/api/v1/tasks")
def list_tasks(request: Request, keyword: str | None = None, model: str | None = None,
               task_type: str | None = None, status: str | None = None,
               canvas_id: int | None = None, node_id: int | None = None,
               canvasId: int | None = None, nodeId: int | None = None,
               date_from: str | None = None, date_to: str | None = None,
               page: int = 1, page_size: int = Query(20, le=100), db: Session = Depends(get_db)):
    uid = user_id(request)
    if uid is None:
        raise HTTPException(status_code=401, detail="未登录")
    # 兼容前端 camelCase（nodeId/canvasId）与 snake_case
    return task_service.list_tasks(
        db, uid, keyword, model, task_type, status,
        canvas_id if canvas_id is not None else canvasId,
        node_id if node_id is not None else nodeId,
        date_from, date_to, page, page_size,
    )


@router.get("/api/v1/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/api/v1/tasks/{task_id}/retry")
def retry_task(task_id: int, db: Session = Depends(get_db)):
    task = task_service.get_task(db, task_id)
    if not task or task["status"] != "failed" or not task["retryable"]:
        raise HTTPException(status_code=400, detail="任务不可重试")
    # 重试走新的计费冻结（前端重新提交），这里仅重新执行
    from ..models import GenerationTask

    t = db.get(GenerationTask, task_id)
    t.status = "queued"
    t.error_code = None
    t.error_message = None
    t.finished_at = None
    t.started_at = None
    db.commit()
    task_service.dispatch(db, task_id)
    return {"status": "queued", "taskId": task_id}


@router.get("/api/v1/tasks/{task_id}/events")
def task_events(task_id: int):
    def event_stream():
        pubsub = redis_client.pubsub()
        pubsub.subscribe(f"task:{task_id}")
        yield f"event: connected\ndata: {json.dumps({'type': 'connected', 'taskId': task_id})}\n\n"
        last = time.time()
        while True:
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                # 使用默认 message 事件，兼容前端 EventSource.onmessage
                yield f"data: {msg['data']}\n\n"
            if time.time() - last > 30:
                yield ": keepalive\n\n"
                last = time.time()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/api/v1/tasks/{task_id}/outputs/file/{file_name}")
def output_file(task_id: int, file_name: str):
    from ..core.config import settings

    path = os.path.join(settings.storage_dir, str(task_id), file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = None
    lower = file_name.lower()
    if lower.endswith(".mp4"):
        media_type = "video/mp4"
    elif lower.endswith(".webm"):
        media_type = "video/webm"
    elif lower.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif lower.endswith(".png"):
        media_type = "image/png"
    elif lower.endswith(".webp"):
        media_type = "image/webp"
    elif lower.endswith(".wav"):
        media_type = "audio/wav"
    elif lower.endswith(".mp3"):
        media_type = "audio/mpeg"
    return FileResponse(path, media_type=media_type)


# ---------- 内部接口 ----------
@router.post("/internal/tasks")
def internal_create_task(body: dict, db: Session = Depends(get_db)):
    return task_service.create_task(db, body)


@router.post("/internal/tasks/cancel")
def internal_cancel_task(body: dict, db: Session = Depends(get_db)):
    task_id = int(body["taskId"])
    reason = body.get("reason", "user_cancel")
    return task_service.cancel(db, task_id, reason)


@router.post("/internal/tasks/{task_id}/expire")
def internal_expire(task_id: int, db: Session = Depends(get_db)):
    return task_service.expire(db, task_id)


@router.get("/internal/models")
def internal_models(type: str | None = None, db: Session = Depends(get_db)):
    return {"items": model_service.list_models(db, type, include_disabled=True)}


@router.post("/internal/models")
def internal_create_model(body: dict, db: Session = Depends(get_db)):
    m = model_service.create(db, body)
    return model_service.to_dict(db, m)


@router.put("/internal/models/{model_id}")
def internal_update_model(model_id: int, body: dict, db: Session = Depends(get_db)):
    m = model_service.update(db, model_id, body)
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    return model_service.to_dict(db, m)


@router.delete("/internal/models/{model_id}")
def internal_delete_model(model_id: int, db: Session = Depends(get_db)):
    if not model_service.delete(db, model_id):
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"status": "ok"}


@router.put("/internal/models/{model_id}/pricing")
def internal_update_pricing(model_id: int, body: dict, db: Session = Depends(get_db)):
    rules = body.get("rules") or []
    m = model_service.update_pricing(db, model_id, rules)
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    return model_service.to_dict(db, m)


@router.get("/health")
def health():
    return {"status": "ok", "service": "generation-service"}
