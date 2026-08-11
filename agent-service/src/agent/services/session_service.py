"""会话服务：创建/列表 + LangGraph 驱动的 run_turn / confirm。"""

from __future__ import annotations

import itertools
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import AgentAction, AgentMessage, AgentSession
from ..tools.registry import TOOLS, headers_for

_id_seq = itertools.count(1)


def coerce_canvas_id(value) -> int | None:
    """把前端/请求体里的 canvasId 规范成 int；拒绝 None/\"None\"。"""
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "undefined"}:
        return None
    try:
        n = int(text)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 1.5))


class SessionService:
    def create_session(self, db: Session, user_id: int, canvas_id: int | None, title: str | None) -> AgentSession:
        # 默认绑定 paper-agent-default
        from .skill_service import skill_service
        skill = skill_service.ensure_paper_agent(db, user_id)
        s = AgentSession(
            id=self.next_id(),
            user_id=user_id,
            canvas_id=coerce_canvas_id(canvas_id),
            title=title or "新对话",
            skill_id=skill.id if skill else None,
            token_used_total=0,
            points_used_total=0,
            model_usage={},
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    def bind_canvas(self, db: Session, session: AgentSession, canvas_id) -> AgentSession:
        cid = coerce_canvas_id(canvas_id)
        if cid and session.canvas_id != cid:
            session.canvas_id = cid
            session.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(session)
        return session

    def list_sessions(self, db: Session, user_id: int, canvas_id: int | None = None):
        q = db.query(AgentSession).filter(AgentSession.user_id == user_id)
        cid = coerce_canvas_id(canvas_id)
        if cid:
            q = q.filter(AgentSession.canvas_id == cid)
        return q.order_by(AgentSession.updated_at.desc()).limit(100).all()

    def get_session(self, db: Session, session_id: int, user_id: int) -> AgentSession | None:
        s = db.get(AgentSession, session_id)
        return s if s and s.user_id == user_id else None

    def messages(self, db: Session, session_id: int):
        return db.query(AgentMessage).filter(AgentMessage.session_id == session_id).order_by(AgentMessage.id).all()

    def add_message(self, db: Session, session_id: int, role: str, content: str,
                    msg_type: str = "text", meta: dict | None = None) -> AgentMessage:
        m = AgentMessage(
            id=self.next_id(),
            session_id=session_id,
            role=role,
            msg_type=msg_type,
            content=content,
            meta=meta or {},
            created_at=datetime.now(timezone.utc),
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        return m

    @staticmethod
    def _is_placeholder_title(title: str | None) -> bool:
        t = (title or "").strip()
        if not t or t in {"新对话", "画布对话"}:
            return True
        if t.startswith("对话 ") or t.startswith("对话#") or t.startswith("对话 #"):
            return True
        return False

    def rename_from_first_user_message(self, db: Session, session: AgentSession, content: str) -> None:
        """对话历史命名：用该会话第一条用户语句。"""
        if not self._is_placeholder_title(session.title):
            return
        text = (content or "").strip()
        if not text:
            return
        user_count = (
            db.query(AgentMessage)
            .filter(AgentMessage.session_id == session.id, AgentMessage.role == "user")
            .count()
        )
        # add_message 已写入本轮，故 == 1 表示首条
        if user_count != 1:
            return
        session.title = text[:48]
        session.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(session)

    def run_turn(self, db: Session, session: AgentSession, content: str,
                 selected_nodes: list[int] | None) -> list[dict]:
        """LangGraph 执行一轮，映射为 SSE 事件。"""
        selected = []
        for x in selected_nodes or []:
            try:
                selected.append(int(x))
            except (TypeError, ValueError):
                continue

        self.add_message(db, session.id, "user", content, "text", {"selectedNodes": selected})
        self.rename_from_first_user_message(db, session, content)

        from ..graph.confirm_helpers import parse_confirm_intent
        from ..graph.app import try_resume_dialog_confirm

        confirm_intent = parse_confirm_intent(content)
        if confirm_intent:
            resumed = try_resume_dialog_confirm(
                session.id, session.user_id, accept=(confirm_intent == "accept"),
            )
            if resumed is not None:
                for e in resumed:
                    if e.get("type") == "assistant_message" and e.get("content"):
                        self.add_message(
                            db, session.id, "assistant", e.get("content") or "",
                            msg_type="text",
                            meta={
                                "replyType": e.get("replyType"),
                                "pipelineStage": e.get("pipelineStage"),
                                "suggestions": e.get("suggestions"),
                                "nextActions": e.get("nextActions"),
                                "executionSteps": e.get("executionSteps"),
                            },
                        )
                session.updated_at = datetime.now(timezone.utc)
                db.commit()
                return resumed

        from ..graph.app import run_agent_turn
        events = run_agent_turn(
            session_id=session.id,
            user_id=session.user_id,
            canvas_id=session.canvas_id,
            content=content,
            selected_nodes=selected,
        )

        # 持久化助手回复（跳过轮询中间态）
        for e in events:
            if e.get("type") == "assistant_message" and e.get("content"):
                self.add_message(
                    db, session.id, "assistant", e.get("content") or "",
                    msg_type="text",
                    meta={
                        "replyType": e.get("replyType"),
                        "pipelineStage": e.get("pipelineStage"),
                        "suggestions": e.get("suggestions"),
                        "nextActions": e.get("nextActions"),
                        "executionSteps": e.get("executionSteps"),
                        "staleNodes": e.get("staleNodes"),
                        "requiresConfirmation": e.get("requiresConfirmation"),
                    },
                )
                tokens = _estimate_tokens(content) + _estimate_tokens(e.get("content") or "")
                session.token_used_total = (session.token_used_total or 0) + tokens
                usage = dict(session.model_usage or {})
                usage["assistant"] = usage.get("assistant", 0) + tokens
                session.model_usage = usage

        session.updated_at = datetime.now(timezone.utc)
        db.commit()

        # 补充 usage 中的累计值
        for e in events:
            if e.get("type") == "usage":
                e["totalTokens"] = session.token_used_total
                e["pointsUsed"] = session.points_used_total
        return events

    def execute_tool(self, db: Session, record: AgentAction, user_id: int, canvas_id: int | None,
                     action, canvas_version: int) -> dict:
        tool = TOOLS.get(action.tool_name)
        if not tool:
            return {"ok": False, "data": {"error": "unknown tool"}}
        params = dict(action.params or {})
        if action.tool_name == "connect_nodes" and canvas_id:
            params["edges"] = self.resolve_edges(db, canvas_id, params.get("edges", []))
        if action.tool_name == "submit_generation":
            params["canvas_id"] = canvas_id
            params["node_id"] = params.get("node_id") or params.pop("nodeId", None)
        try:
            data = tool.fn(canvas_id=canvas_id, user_id=user_id, **params)
            ok = "error" not in data
            record.status = "executed" if ok else "failed"
            record.result = data
            record.error_code = "TOOL_ERROR" if not ok else None
            if action.tool_name == "submit_generation" and ok and data.get("estimatedCost"):
                session = db.get(AgentSession, record.session_id)
                if session:
                    session.points_used_total += int(data["estimatedCost"])
            db.commit()
            return {"ok": ok, "data": data}
        except Exception as e:
            record.status = "failed"
            record.error_code = "TOOL_ERROR"
            record.result = {"error": str(e)[:300]}
            db.commit()
            return {"ok": False, "data": {"error": str(e)[:300]}}

    def resolve_edges(self, db: Session, canvas_id: int, edges: list[dict]) -> list[dict]:
        """仅清洗已有 edges；不再猜测随机连线（避免 director→compose 等非法边）。"""
        cleaned = []
        for e in edges or []:
            src = e.get("sourceNodeId") if e.get("sourceNodeId") is not None else e.get("source")
            tgt = e.get("targetNodeId") if e.get("targetNodeId") is not None else e.get("target")
            try:
                src_i = int(src) if src is not None else 0
                tgt_i = int(tgt) if tgt is not None else 0
            except (TypeError, ValueError):
                continue
            if src_i <= 0 or tgt_i <= 0 or src_i == tgt_i:
                continue
            cleaned.append({
                "sourceNodeId": src_i,
                "targetNodeId": tgt_i,
                "sourcePort": e.get("sourcePort", "output"),
                "targetPort": e.get("targetPort", "input"),
                "dependencyType": e.get("dependencyType") or e.get("dependency_type") or "input",
            })
        return cleaned

    def confirm(self, db: Session, session_id: int, user_id: int, action_id: int, token: str,
                accept: bool) -> dict:
        from ..graph.app import resume_agent_confirm
        return resume_agent_confirm(session_id, user_id, action_id, accept)

    def build_reply(self, actions, executed, pending_tokens) -> str:
        lines = [f"- {a.summary}" for a in actions]
        if pending_tokens:
            lines.append(f"\n⚠️ {len(pending_tokens)} 个操作需要确认")
        else:
            lines.append("\n✅ 已执行完成，请查看画布。")
        return "\n".join(lines)

    @staticmethod
    def next_id() -> int:
        return (int(time.time() * 1000) << 20) | (next(_id_seq) & 0xFFFFF)


session_service = SessionService()
