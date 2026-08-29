"""三层记忆系统（§3.11）：长期记忆 + 当日记忆 + 项目记忆。

核心设计：
- Agent 只负责判断"这条该归哪层、值不值得记"，通过 update_memory 触发异步写入。
- 去重/合并/压缩交给子 Agent 异步完成，Agent 不等待、不汇报。
- 画布即外部存储：不把画布节点内容复制进记忆，需要时用 read 去取。
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

import redis
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..core.config import settings
from ..domain.hashed_embedding import cosine_similarity, hashed_embedding
from ..models import SessionFragment, UserMemory
from .session_service import session_service

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)

# 当日记忆 TTL：24 小时，次日自动失效
DAILY_TTL = 86400
# 长期记忆压缩阈值
LONG_TERM_COMPRESS_THRESHOLD = 50
# 去重相似度阈值（简单向量余弦）
DEDUP_SIMILARITY_THRESHOLD = 0.85


def _simple_vector(text: str) -> list[float]:
    """兼容旧函数名；返回带稳定词维度的归一化向量。"""
    return hashed_embedding(text)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    return cosine_similarity(a, b)


class MemoryService:
    # ── 读取 ──────────────────────────────────────────────

    def short_term(self, session_id: int) -> dict:
        """读取短期工作记忆（Redis，会话级上下文）。"""
        raw = redis_client.get(f"agent_ctx:{session_id}")
        return json.loads(raw) if raw else {}

    def update_short_term(self, session_id: int, content: str):
        """更新短期工作记忆，只保留最近 10 条。"""
        ctx = self.short_term(session_id)
        ctx["lastMessages"] = (ctx.get("lastMessages") or [])[-10:] + [content[:500]]
        redis_client.setex(f"agent_ctx:{session_id}", 1800, json.dumps(ctx, ensure_ascii=False))

    def list_long_term(self, db: Session, user_id: int):
        """读取长期记忆（跨画布偏好）。"""
        now = datetime.now(timezone.utc)
        return (
            db.query(UserMemory)
            .filter(
                UserMemory.user_id == user_id,
                UserMemory.scope == "long_term",
                UserMemory.deleted.is_(False),
                or_(UserMemory.expires_at.is_(None), UserMemory.expires_at > now),
            )
            .order_by(UserMemory.created_at.desc())
            .all()
        )

    def list_daily(self, user_id: int) -> list[dict]:
        """读取当日记忆（Redis，次日失效）。"""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        raw = redis_client.get(f"agent_daily:{user_id}:{today}")
        return json.loads(raw) if raw else []

    def list_project_fragments(self, db: Session, canvas_id: int) -> list[SessionFragment]:
        """读取项目记忆（绑定当前画布）。"""
        return (
            db.query(SessionFragment)
            .filter(SessionFragment.canvas_id == canvas_id)
            .order_by(SessionFragment.created_at.desc())
            .all()
        )

    # ── 写入：三层 + 三关判据 ────────────────────────────

    def add(self, db: Session, user_id: int, content: str,
            memory_type: str = "preference", scope: str = "long_term") -> UserMemory:
        """直接写入长期/当日记忆（底层方法，不经过三关判据）。"""
        mem = UserMemory(
            id=session_service.next_id(),
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            scope=scope,
            embedding=_simple_vector(content),
            created_at=datetime.now(timezone.utc),
        )
        db.add(mem)
        db.commit()
        db.refresh(mem)
        return mem

    def add_daily(self, user_id: int, content: str, memory_type: str = "temp"):
        """写入当日记忆（Redis，TTL=24h）。"""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"agent_daily:{user_id}:{today}"
        raw = redis_client.get(key)
        items = json.loads(raw) if raw else []
        items.append({"content": content[:500], "type": memory_type, "ts": datetime.now(timezone.utc).isoformat()})
        redis_client.setex(key, DAILY_TTL, json.dumps(items, ensure_ascii=False))

    def add_project_fragment(self, db: Session, owner_id: int, canvas_id: int,
                             title: str, content: dict, fragment_type: str = "worldview") -> SessionFragment:
        """写入项目记忆（绑定画布）。"""
        frag = SessionFragment(
            id=session_service.next_id(),
            owner_id=owner_id,
            title=title,
            content=content,
            canvas_id=canvas_id,
            fragment_type=fragment_type,
            created_at=datetime.now(timezone.utc),
        )
        db.add(frag)
        db.commit()
        db.refresh(frag)
        return frag

    # ── update_memory：异步触发，不等待 ──────────────────

    def trigger_memory_update(self, user_id: int, canvas_id: Optional[int],
                              scope: str, content: str, fragment_type: str = "worldview"):
        """触发异步记忆更新（Agent 调用此方法后立即返回，不等待）。

        实际的去重、合并、压缩由记忆子 Agent 异步完成。
        V1.0 用 Celery 异步任务实现，P1 迁移到 LangGraph 子图。
        """
        try:
            from ..core.config import settings as cfg
            if cfg.redis_url:
                # V1.0: 通过 Redis 队列触发异步任务
                task = json.dumps({
                    "user_id": user_id,
                    "canvas_id": canvas_id,
                    "scope": scope,
                    "content": content[:2000],
                    "fragment_type": fragment_type,
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False)
                redis_client.lpush("memory_update_queue", task)
        except Exception:
            pass  # 记忆写入失败不影响主流程

    def process_memory_update(self, db: Session, task: dict):
        """记忆子 Agent 执行：去重 → 合并 → 压缩。

        由 Celery worker 或 LangGraph 子图调用，不在主流程中执行。
        """
        user_id = task["user_id"]
        canvas_id = task.get("canvas_id")
        scope = task["scope"]
        content = task["content"]
        fragment_type = task.get("fragment_type", "worldview")

        if scope == "long_term":
            self._merge_long_term(db, user_id, content)
        elif scope == "daily":
            self.add_daily(user_id, content)
        elif scope == "project" and canvas_id:
            self._merge_project_fragment(db, user_id, canvas_id, content, fragment_type)

    def _merge_long_term(self, db: Session, user_id: int, content: str):
        """长期记忆去重合并：与已有记忆做语义比对，重复则更新，否则新增。"""
        existing = self.list_long_term(db, user_id)
        new_vec = _simple_vector(content)

        for mem in existing:
            sim = _cosine_similarity(new_vec, mem.embedding or [])
            if sim >= DEDUP_SIMILARITY_THRESHOLD:
                # 语义重复：更新内容，保留原 id
                mem.content = content
                mem.embedding = new_vec
                mem.last_merged_at = datetime.now(timezone.utc)
                db.commit()
                return

        # 不重复：新增
        self.add(db, user_id, content, scope="long_term")

        # 检查是否需要压缩
        if len(existing) >= LONG_TERM_COMPRESS_THRESHOLD:
            self._compress_long_term(db, user_id)

    def _merge_project_fragment(self, db: Session, owner_id: int, canvas_id: int,
                                content: str, fragment_type: str):
        """项目记忆去重合并：同类型片段做语义比对。"""
        existing = (
            db.query(SessionFragment)
            .filter(
                SessionFragment.canvas_id == canvas_id,
                SessionFragment.fragment_type == fragment_type,
            )
            .all()
        )
        new_vec = _simple_vector(content)

        for frag in existing:
            frag_text = json.dumps(frag.content or {}, ensure_ascii=False)
            sim = _cosine_similarity(new_vec, _simple_vector(frag_text))
            if sim >= DEDUP_SIMILARITY_THRESHOLD:
                frag.content = {"summary": content[:1000]}
                frag.created_at = datetime.now(timezone.utc)
                db.commit()
                return

        self.add_project_fragment(
            db, owner_id, canvas_id,
            title=f"{fragment_type} summary",
            content={"summary": content[:1000]},
            fragment_type=fragment_type,
        )

    def _compress_long_term(self, db: Session, user_id: int):
        """长期记忆压缩：合并同类项，保留最新。"""
        all_memories = self.list_long_term(db, user_id)
        if len(all_memories) < LONG_TERM_COMPRESS_THRESHOLD:
            return

        # 按 memory_type 分组，每组保留最新的 N 条
        groups: dict[str, list] = {}
        for mem in all_memories:
            groups.setdefault(mem.memory_type, []).append(mem)

        for mem_type, items in groups.items():
            if len(items) > 10:
                # 删除较旧的，保留最新 10 条
                for old in items[10:]:
                    db.delete(old)
        db.commit()

    # ── 三关判据 ──────────────────────────────────────────

    @staticmethod
    def should_remember(result: dict, state: dict) -> bool:
        """三关检查：跨轮需要 + 归属明确 + 画布没有。"""
        # 关1：是否跨轮需要（一次性信息不写）
        if not MemoryService._is_cross_turn_relevant(result, state):
            return False
        # 关2：能否明确归属层级
        scope = MemoryService.classify_scope(result, state)
        if scope is None:
            return False
        # 关3：画布上是否已有（不重复存画布内容）
        if MemoryService._already_on_canvas(result, state):
            return False
        return True

    @staticmethod
    def _is_cross_turn_relevant(result: dict, state: dict) -> bool:
        """判断信息是否在后续轮次还要用到。"""
        tool = result.get("tool", "")
        # 用户偏好/风格设定 → 跨轮
        if tool in ("change_model", "update_node_config"):
            return True
        # 一次性生成结果 → 不跨轮（结果在画布节点里）
        if tool == "submit_generation":
            return False
        # 角色卡/脚本创建 → 跨轮
        if tool == "create_nodes":
            nodes = result.get("data", {}).get("nodes", [])
            creative_types = {"script", "character", "shot"}
            return any(n.get("creative_type") in creative_types for n in nodes)
        return False

    @staticmethod
    def classify_scope(result: dict, state: dict) -> Optional[str]:
        """判断信息归属层级：long_term / daily / project / None。"""
        tool = result.get("tool", "")
        # 用户切换模型偏好 → 长期
        if tool == "change_model":
            return "long_term"
        # 角色卡/脚本/风格设定 → 项目
        if tool == "create_nodes":
            nodes = result.get("data", {}).get("nodes", [])
            creative_types = {"script", "character", "shot"}
            if any(n.get("creative_type") in creative_types for n in nodes):
                return "project"
        # 修改节点参数 → 看改的是什么
        if tool == "update_node_config":
            return "project"
        return None

    @staticmethod
    def _already_on_canvas(result: dict, state: dict) -> bool:
        """判断信息是否已在画布节点里（不重复存）。"""
        tool = result.get("tool", "")
        # 脚本/角色卡内容已在画布节点里
        if tool == "create_nodes":
            return True  # 节点内容就是画布上的，不复制进记忆
        return False

    # ── 删除 ──────────────────────────────────────────────

    def delete(self, db: Session, memory_id: int, user_id: int) -> bool:
        mem = db.get(UserMemory, memory_id)
        if not mem or mem.user_id != user_id or mem.deleted:
            return False
        mem.deleted = True
        db.commit()
        return True

    def delete_daily(self, user_id: int):
        """清除当日记忆。"""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        redis_client.delete(f"agent_daily:{user_id}:{today}")

    # ── 兼容旧接口 ────────────────────────────────────────

    def extract_preferences(self, db: Session, user_id: int, content: str) -> list[UserMemory]:
        """从对话中提取长期记忆（V1.0 规则匹配，P1 由 LLM 子 Agent 替换）。"""
        created = []
        rules = [
            (r"喜欢|偏好", "preference"),
            (r"风格|画风|色调", "style"),
            (r"习惯|通常|每次", "habit"),
        ]
        for pattern, mem_type in rules:
            if re.search(pattern, content):
                created.append(self.add(db, user_id, content[:300], memory_type=mem_type, scope="long_term"))
        return created


memory_service = MemoryService()
