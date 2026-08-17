import json
import time

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import get_db
from ..models import SessionFragment
from ..services.memory_service import memory_service
from ..services.session_service import session_service
from ..services.skill_service import skill_service

router = APIRouter()


def user_id(request: Request) -> int:
    raw = request.headers.get("X-User-Id")
    if not raw:
        raise HTTPException(status_code=401, detail="未登录")
    return int(raw)


def _sse_chunk_text(content: str, *, fine: bool = False) -> tuple[int, float]:
    """返回 (step, delay)：控制分片粒度，总时长约 0.8–2.5s。"""
    n = len(content)
    if fine:
        # 正式回复：更细，方便前端逐字感
        chunks = max(24, min(160, n))
        step = max(1, n // chunks)
        delay = min(0.03, max(0.012, 2.0 / max(chunks, 1)))
        return step, delay
    chunks = max(16, min(80, n // 2 or 16))
    step = max(4, n // chunks)
    delay = min(0.035, max(0.018, 1.6 / max(chunks, 1)))
    return step, delay


def sse(events: list[dict]):
    """SSE 管道：thinking / 正式回复按累计前缀分片推送，避免整包「啪一下」。"""

    def _emit(e: dict):
        return f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"

    def _stream_text_event(e: dict, content: str, *, fine: bool) -> None:
        step, delay = _sse_chunk_text(content, fine=fine)
        # 中间片只带正文，最终片带齐 meta（executionSteps 等）
        light = {k: v for k, v in e.items() if k not in ("executionSteps", "suggestions", "nextActions")}
        for i in range(step, len(content), step):
            yield _emit({**light, "content": content[:i], "streaming": True})
            time.sleep(delay)
        yield _emit({**e, "content": content, "streaming": False})
        time.sleep(0.03)

    def stream():
        for e in events:
            et = e.get("type")
            content = e.get("content")
            if et in ("thinking", "reflection") and isinstance(content, str) and len(content) > 16:
                yield from _stream_text_event(e, content, fine=False)
            elif et == "assistant_message" and isinstance(content, str) and len(content) > 8:
                yield from _stream_text_event(e, content, fine=True)
            else:
                yield _emit(e)
                time.sleep(0.05)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/v1/agent/sessions")
def create_session(request: Request, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    s = session_service.create_session(db, uid,
                                       body.get("canvasId") or body.get("canvas_id"),
                                       body.get("title"))
    return {"sessionId": s.id, "title": s.title, "canvasId": s.canvas_id}


@router.get("/api/v1/agent/sessions")
def list_sessions(request: Request, canvasId: str | None = None, db: Session = Depends(get_db)):
    uid = user_id(request)
    return {"items": [{"sessionId": s.id, "title": s.title, "canvasId": s.canvas_id,
                       "updatedAt": s.updated_at.isoformat() if s.updated_at else None}
                      for s in session_service.list_sessions(db, uid, canvasId)]}


@router.get("/api/v1/agent/sessions/{session_id}")
def get_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    uid = user_id(request)
    s = session_service.get_session(db, session_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"sessionId": s.id, "title": s.title, "canvasId": s.canvas_id, "status": s.status}


@router.get("/api/v1/agent/sessions/{session_id}/messages")
def get_messages(request: Request, session_id: int, db: Session = Depends(get_db)):
    uid = user_id(request)
    s = session_service.get_session(db, session_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"items": [{"id": m.id, "role": m.role, "type": m.msg_type, "content": m.content,
                       "meta": m.meta, "createdAt": m.created_at.isoformat()}
                      for m in session_service.messages(db, session_id)]}


@router.post("/api/v1/agent/sessions/{session_id}/messages")
def send_message(request: Request, session_id: int, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    s = session_service.get_session(db, session_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 前端每次带上 canvasId，补绑到会话，避免历史会话 canvas_id 为空
    s = session_service.bind_canvas(db, s, body.get("canvasId") or body.get("canvas_id"))
    if not s.canvas_id:
        raise HTTPException(status_code=400, detail="会话未绑定画布，请在画布页重新打开 Agent")
    content = body.get("content", "")
    selected = body.get("selectedNodeIds")
    events = session_service.run_turn(db, s, content, selected)
    memory_service.update_short_term(session_id, content)
    return sse(events)


@router.post("/api/v1/agent/sessions/{session_id}/confirmations/{action_id}")
def confirm(request: Request, session_id: str, action_id: str, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    try:
        sid = int(session_id)
        aid = int(action_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "非法会话或确认 ID", "retryable": False},
        )
    result = session_service.confirm(
        db, sid, uid, aid,
        body.get("token", ""),
        bool(body.get("accept", False)),
        confirmed_action=body.get("confirmedAction") or body.get("confirmed_action") or body.get("params"),
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": result.get("error_code") or "CONFIRMATION_REQUIRED",
                "message": result.get("error") or "确认失败",
                "retryable": False,
            },
        )
    return result


@router.get("/api/v1/agent/sessions/{session_id}/usage")
def usage(request: Request, session_id: int, db: Session = Depends(get_db)):
    uid = user_id(request)
    s = session_service.get_session(db, session_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"sessionId": s.id, "tokenTotal": s.token_used_total, "pointsUsed": s.points_used_total,
            "modelUsage": s.model_usage or {}}


# ---------- Skill ----------
@router.get("/api/v1/skills")
def list_skills(
    request: Request,
    keyword: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    uid = user_id(request)
    from ..services.skill_service import skill_to_dict

    skill_service.ensure_builtin_skills(db)
    items = skill_service.list(db, uid, keyword, category=category, include_disabled=True)
    return {"items": [skill_to_dict(s) for s in items]}


@router.get("/api/v1/skills/{skill_id}")
def get_skill(request: Request, skill_id: int, db: Session = Depends(get_db)):
    uid = user_id(request)
    from ..services.skill_service import skill_to_dict

    skill_service.ensure_builtin_skills(db)
    s = skill_service.get(db, skill_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    return skill_to_dict(s)


@router.post("/api/v1/skills")
def create_skill(request: Request, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    from ..services.skill_service import skill_to_dict

    try:
        s = skill_service.create(
            db, uid, body["name"], body.get("description"), body["instructions"],
            category=body.get("category") or "general",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return skill_to_dict(s)


@router.post("/api/v1/skills/from-conversation")
def skill_from_conversation(request: Request, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    from ..services.skill_service import skill_to_dict

    s = skill_service.from_conversation(db, uid, int(body["sessionId"]), body.get("name"))
    return skill_to_dict(s)


@router.post("/api/v1/skills/upload")
async def upload_skill(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    uid = user_id(request)
    from ..services.skill_service import skill_to_dict

    content = await file.read()
    try:
        s = skill_service.upload(db, uid, file.filename or "skill.md", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return skill_to_dict(s)


@router.post("/api/v1/skills/{skill_id}/attach")
def attach_skill(request: Request, skill_id: int, sessionId: int, db: Session = Depends(get_db)):
    uid = user_id(request)
    skill = skill_service.get(db, skill_id, uid)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    s = session_service.get_session(db, sessionId, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    s.skill_id = skill_id
    db.commit()
    return {"status": "ok", "sessionId": s.id, "skillId": skill_id}


@router.put("/api/v1/skills/{skill_id}")
def update_skill(request: Request, skill_id: int, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    from ..services.skill_service import skill_to_dict

    try:
        s = skill_service.update(
            db, skill_id, uid,
            body.get("name"), body.get("description"), body.get("instructions"),
            enabled=body.get("enabled"),
            category=body.get("category"),
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not s:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    return skill_to_dict(s)


@router.delete("/api/v1/skills/{skill_id}")
def delete_skill(request: Request, skill_id: int, db: Session = Depends(get_db)):
    uid = user_id(request)
    skill = skill_service.get(db, skill_id, uid)
    if skill is None:
        from ..models import Skill
        builtin = db.get(Skill, skill_id)
        if builtin and builtin.source == "builtin":
            raise HTTPException(status_code=403, detail="内置 Skill 不可删除")
        raise HTTPException(status_code=404, detail="Skill 不存在")
    if skill.source == "builtin":
        raise HTTPException(status_code=403, detail="内置 Skill 不可删除")
    if not skill_service.delete(db, skill_id, uid):
        raise HTTPException(status_code=404, detail="Skill 不存在")
    return {"status": "ok"}


@router.get("/api/v1/agent/sessions/{session_id}/events")
def session_events(request: Request, session_id: int, db: Session = Depends(get_db)):
    """持久 SSE：订阅 clock 唤醒 / 任务完成推送。"""
    uid = user_id(request)
    s = session_service.get_session(db, session_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")

    import redis
    from ..services.session_events import sse_channel

    r = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)

    def stream():
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(sse_channel(session_id))
        yield f"event: connected\ndata: {json.dumps({'sessionId': session_id}, ensure_ascii=False)}\n\n"
        last_ping = time.time()
        while True:
            msg = pubsub.get_message(timeout=1.0)
            if msg and msg.get("type") == "message":
                raw = msg.get("data")
                try:
                    ev = json.loads(raw)
                    ev_type = ev.get("type", "message")
                    yield f"event: {ev_type}\ndata: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
                except Exception:
                    yield f"event: message\ndata: {json.dumps({'type': 'raw', 'data': raw}, ensure_ascii=False)}\n\n"
            if time.time() - last_ping > 25:
                yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n"
                last_ping = time.time()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/v1/agent/sessions/{session_id}/notifications")
def pull_notifications(request: Request, session_id: int, db: Session = Depends(get_db)):
    """拉取 clock 唤醒等异步通知（任务完成/失败）。"""
    uid = user_id(request)
    s = session_service.get_session(db, session_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    import redis
    from ..core.config import settings
    r = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)
    items = []
    while len(items) < 20:
        raw = r.rpop(f"agent_session_notify:{session_id}")
        if not raw:
            break
        try:
            items.append(json.loads(raw))
        except Exception:
            items.append({"type": "raw", "data": raw})
    return {"items": items}


# ---------- 记忆 ----------
@router.get("/api/v1/memories")
def list_memories(request: Request, db: Session = Depends(get_db)):
    uid = user_id(request)
    return {"items": [{"id": m.id, "content": m.content, "memoryType": m.memory_type,
                       "createdAt": m.created_at.isoformat()}
                      for m in memory_service.list_long_term(db, uid)]}


@router.post("/api/v1/memories")
def add_memory(request: Request, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    m = memory_service.add(db, uid, body["content"], body.get("memoryType", "preference"))
    return {"id": m.id, "content": m.content}


@router.delete("/api/v1/memories/{memory_id}")
def delete_memory(request: Request, memory_id: int, db: Session = Depends(get_db)):
    uid = user_id(request)
    if not memory_service.delete(db, memory_id, uid):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"status": "ok"}


# ---------- 会话片段 ----------
@router.post("/api/v1/agent/sessions/{session_id}/fragments")
def save_fragment(request: Request, session_id: int, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    s = session_service.get_session(db, session_id, uid)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = [{"role": m.role, "content": m.content} for m in session_service.messages(db, session_id)]
    frag = SessionFragment(id=session_service.next_id(), owner_id=uid,
                           title=body.get("title") or s.title,
                           content=msgs, canvas_id=s.canvas_id,
                           created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    db.add(frag)
    db.commit()
    return {"fragmentId": frag.id}


@router.get("/api/v1/agent/fragments")
def list_fragments(request: Request, db: Session = Depends(get_db)):
    uid = user_id(request)
    frags = db.query(SessionFragment).filter(SessionFragment.owner_id == uid).order_by(SessionFragment.id.desc()).all()
    return {"items": [{"id": f.id, "title": f.title, "canvasId": f.canvas_id,
                       "createdAt": f.created_at.isoformat()} for f in frags]}


@router.post("/api/v1/agent/fragments/{fragment_id}/import")
def import_fragment(request: Request, fragment_id: int, body: dict, db: Session = Depends(get_db)):
    uid = user_id(request)
    frag = db.get(SessionFragment, fragment_id)
    if not frag or frag.owner_id != uid:
        raise HTTPException(status_code=404, detail="片段不存在")
    s = session_service.create_session(db, uid, body.get("canvasId"), frag.title)
    for m in (frag.content or []):
        session_service.add_message(db, s.id, m.get("role", "user"), m.get("content", ""))
    return {"sessionId": s.id}


@router.get("/health")
def health():
    return {"status": "ok", "service": "agent-service"}
