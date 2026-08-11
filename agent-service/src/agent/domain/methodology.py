"""七大工作方式硬审计。

原则写在 persona 里只是契约文案；本模块把每条落成可对 PlanResult / 动作序列
做断言的规则，供规划路径自检与回归测试使用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..agent.planner import PlannedAction, PlanResult

# 创意术语：对用户话术应出现；内部 id / 工具名不应出现
CREATIVE_TERMS = ("分镜", "镜头", "首帧", "脚本", "成片", "运镜", "节奏", "关键帧", "节点")
INTERNAL_LEAK_RE = re.compile(
    r"(节点\s*\d+|node_id\s*[=:]\s*\d+|task_id\s*[=:]|\$created\[|tool_name|execStatus)",
    re.I,
)
VERBATIM_FORBIDDEN_PREFIXES = (
    "帮我", "请帮我", "做一个", "做个", "搭建", "编排", "添加到画布",
)


@dataclass
class PrincipleFinding:
    principle: int
    name: str
    ok: bool
    detail: str = ""


@dataclass
class MethodologyReport:
    findings: list[PrincipleFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    def failed(self) -> list[PrincipleFinding]:
        return [f for f in self.findings if not f.ok]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [
                {"principle": f.principle, "name": f.name, "ok": f.ok, "detail": f.detail}
                for f in self.findings
            ],
        }


def _actions_of(plan: PlanResult | Iterable[PlannedAction] | list[dict]) -> list[Any]:
    if isinstance(plan, PlanResult):
        return list(plan.actions or [])
    return list(plan or [])


def _tool(a: Any) -> str:
    if isinstance(a, PlannedAction):
        return a.tool_name
    return str(a.get("tool_name") or a.get("tool") or "")


def _params(a: Any) -> dict:
    if isinstance(a, PlannedAction):
        return dict(a.params or {})
    return dict(a.get("params") or {})


def _summary(a: Any) -> str:
    if isinstance(a, PlannedAction):
        return a.summary or ""
    return str(a.get("summary") or "")


def _created_nodes(actions: list[Any]) -> list[dict]:
    nodes: list[dict] = []
    for a in actions:
        if _tool(a) != "create_nodes":
            continue
        nodes.extend(_params(a).get("nodes") or [])
    return nodes


def _input_edges(actions: list[Any]) -> list[dict]:
    edges: list[dict] = []
    for a in actions:
        if _tool(a) != "connect_nodes":
            continue
        for e in _params(a).get("edges") or []:
            dep = e.get("dependencyType") or e.get("dependency_type") or "reference"
            if dep == "input":
                edges.append(e)
    return edges


def _submits(actions: list[Any]) -> list[Any]:
    return [a for a in actions if _tool(a) in ("submit_generation", "compose_final", "upscale")]


def _node_prompt(node: dict) -> str:
    params = node.get("params") or {}
    return str(node.get("prompt") or params.get("prompt") or "").strip()


def _type_matches_product(node: dict) -> bool:
    """产物决定节点类型（原则三）。"""
    ntype = str(node.get("type") or "")
    creative = str(node.get("creativeType") or node.get("creative_type") or "")
    expect = {
        "keyframe": "image",
        "clip": "video",
        "script": "text",
        "shot": "text",
        "character": "text",
        "audio": "audio",
        "composite": "compose",
    }
    if creative in expect:
        return ntype == expect[creative]
    if ntype in ("image", "video", "audio", "text", "compose", "director"):
        return True
    return False


def audit_orchestration_actions(
    actions: list[Any],
    *,
    reply: str = "",
    thinking: str = "",
    user_content: str = "",
    expect_multi_unit: bool = False,
) -> MethodologyReport:
    """对一次编排动作序列做七大原则审计。"""
    findings: list[PrincipleFinding] = []
    tools = [_tool(a) for a in actions]
    nodes = _created_nodes(actions)
    edges = _input_edges(actions)
    submits = _submits(actions)
    prompts = [_node_prompt(n) for n in nodes if _node_prompt(n)]

    # 一、先拆解再执行：建节点 → 连线 → 再 submit；禁止只有空话没有动作（编排场景）
    create_idx = next((i for i, t in enumerate(tools) if t == "create_nodes"), None)
    submit_idx = next((i for i, t in enumerate(tools) if t in ("submit_generation", "compose_final")), None)
    connect_idx = next((i for i, t in enumerate(tools) if t == "connect_nodes"), None)
    order_ok = True
    detail1 = "动作顺序符合：建节点→连线→提交"
    if create_idx is None and expect_multi_unit:
        order_ok = False
        detail1 = "编排请求未创建任何节点"
    elif create_idx is not None and submit_idx is not None and create_idx > submit_idx:
        order_ok = False
        detail1 = "先提交后建节点，违反动作优先循环"
    elif create_idx is not None and connect_idx is not None and len(nodes) >= 2 and connect_idx < create_idx:
        # 允许先读摘要再 create；不允许 connect 早于首次 create
        order_ok = False
        detail1 = "连线早于建节点"
    findings.append(PrincipleFinding(1, "先拆解再执行", order_ok, detail1))

    # 二、按产物边界切：多单元链路必须拆出多种 creativeType / 多个独立节点
    creatives = {str(n.get("creativeType") or n.get("creative_type") or "") for n in nodes}
    creatives.discard("")
    if expect_multi_unit:
        boundary_ok = len(nodes) >= 3 and len(creatives) >= 3
        detail2 = f"节点数={len(nodes)} creativeTypes={sorted(creatives)}"
    else:
        boundary_ok = True
        if nodes:
            # 单请求也要求「一个节点一件事」：不得把分镜+视频塞进同一节点
            mashed = any(
                ("分镜" in _node_prompt(n) and n.get("type") == "video")
                or ("所有镜头" in _node_prompt(n) or "全部画面" in _node_prompt(n))
                for n in nodes
            )
            boundary_ok = not mashed
        detail2 = "单节点一事" if boundary_ok else "存在把多镜头/分镜塞进单一生成节点"
    findings.append(PrincipleFinding(2, "按产物边界切", boundary_ok, detail2))

    # 三、产物决定节点类型
    type_ok = all(_type_matches_product(n) for n in nodes) if nodes else True
    bad_types = [
        f"{n.get('creativeType')}≠{n.get('type')}"
        for n in nodes if not _type_matches_product(n)
    ]
    findings.append(PrincipleFinding(
        3, "产物决定节点类型", type_ok,
        "类型匹配" if type_ok else f"不匹配: {bad_types}",
    ))

    # 四、连线表达依赖
    if len(nodes) >= 2:
        edge_ok = len(edges) >= 1 and all(
            (e.get("dependencyType") or e.get("dependency_type")) == "input" for e in edges
        )
        detail4 = f"input 连线 {len(edges)} 条" if edge_ok else "多节点却缺少 input 依赖连线"
    else:
        edge_ok = True
        detail4 = "单节点无需连线"
    findings.append(PrincipleFinding(4, "连线表达依赖", edge_ok, detail4))

    # 五、每节点独立 prompt：非用户原话、彼此不同、说清本次产物
    prompt_ok = True
    detail5 = "各节点 Prompt 独立"
    if nodes:
        if len(prompts) < len(nodes):
            prompt_ok = False
            detail5 = "存在节点缺少 Prompt"
        elif len(set(prompts)) != len(prompts):
            prompt_ok = False
            detail5 = "存在重复 Prompt（未按镜头/角色独立撰写）"
        elif user_content and any(p == user_content.strip() for p in prompts):
            prompt_ok = False
            detail5 = "Prompt 原样复制用户原话"
        elif any(len(p) < 20 for p in prompts):
            prompt_ok = False
            detail5 = "存在过短 Prompt（未说清本次要什么）"
        elif user_content and any(
            p.startswith(prefix) for p in prompts for prefix in VERBATIM_FORBIDDEN_PREFIXES
        ):
            prompt_ok = False
            detail5 = "Prompt 以指令前缀开头，未写成产物描述"
    findings.append(PrincipleFinding(5, "每节点独立 prompt", prompt_ok, detail5))

    # 六、异步纪律：依赖未就绪不盲提交；回复不把 queued 说成已完成
    submit_targets = []
    for a in submits:
        p = _params(a)
        submit_targets.append(str(p.get("node_id") or p.get("nodeId") or ""))
    # 短剧/图生视频：同轮若新建了 video，且 video 依赖同轮新建的 image，则不得 submit video
    created_video_idxs = [i for i, n in enumerate(nodes) if n.get("type") == "video"]
    created_image_idxs = [i for i, n in enumerate(nodes) if n.get("type") == "image"]
    async_ok = True
    detail6 = "仅提交当前可跑节点"
    if created_video_idxs and created_image_idxs:
        # 若存在 image→video 的边，则 submit 不得指向 video
        for e in edges:
            src = str(e.get("sourceNodeId") or e.get("source") or "")
            tgt = str(e.get("targetNodeId") or e.get("target") or "")
            src_m = re.search(r"\$created\[(\d+)\]", src)
            tgt_m = re.search(r"\$created\[(\d+)\]", tgt)
            if not (src_m and tgt_m):
                continue
            si, ti = int(src_m.group(1)), int(tgt_m.group(1))
            if si in created_image_idxs and ti in created_video_idxs:
                for a in submits:
                    nid = str(_params(a).get("node_id") or "")
                    if nid == f"$created[{ti}]" or (
                        _params(a).get("model_type") == "video" and "待" not in _summary(a)
                        and nid == f"$created[{ti}]"
                    ):
                        async_ok = False
                        detail6 = "上游首帧尚未生成就提交了视频"
        # 更强约束：同轮创建了 image+video 时，submit 只应指向 image（或 text 根），不应有 video submit
        video_submits = [
            a for a in submits
            if _params(a).get("model_type") == "video" or _tool(a) == "compose_final"
        ]
        # compose 在短剧 bootstrap 不应同轮提交
        if any(_params(a).get("model_type") == "video" for a in submits):
            # 允许：仅当没有同轮 image→video 边（已有选中就绪图）
            has_live_iv_edge = any(
                re.search(r"\$created\[(\d+)\]", str(e.get("sourceNodeId") or ""))
                and int(re.search(r"\$created\[(\d+)\]", str(e.get("sourceNodeId") or "")).group(1))
                in created_image_idxs
                for e in edges
                if re.search(r"\$created\[(\d+)\]", str(e.get("sourceNodeId") or ""))
            )
            if has_live_iv_edge:
                async_ok = False
                detail6 = "同轮新建了首帧→视频依赖，却仍提交了视频"
    # 回复不得编造成品
    finished_claim = bool(re.search(
        r"(已经生成好了|生成完成了|成品如下|视频已就绪|图片已生成完毕|这是生成结果)",
        reply or "",
    ))
    if finished_claim and submits:
        async_ok = False
        detail6 = "回复把 queued/提交说成已完成成品"
    findings.append(PrincipleFinding(6, "异步不编造按状态行动", async_ok, detail6))

    # 七、三条纪律：缺了才查 / 有主见用语 / 不暴露内部 id
    read_tools = [t for t in tools if t.startswith(("get_", "list_", "search_"))]
    # 编排场景允许多 1 次 get_canvas_summary；禁止连环空读
    discipline_ok = True
    detail7 = "对用户用语与查询纪律合规"
    if read_tools.count("get_canvas_summary") > 2:
        discipline_ok = False
        detail7 = "反复 get_canvas_summary，违反「缺了才查」"
    user_facing = f"{reply or ''}\n{thinking or ''}"
    if user_facing and INTERNAL_LEAK_RE.search(user_facing):
        discipline_ok = False
        detail7 = "对用户文本暴露了内部节点 id / 占位符"
    if expect_multi_unit and reply and not any(term in reply for term in CREATIVE_TERMS):
        discipline_ok = False
        detail7 = "编排回复缺少创作术语（分镜/镜头/首帧等）"
    findings.append(PrincipleFinding(7, "三条纪律", discipline_ok, detail7))

    return MethodologyReport(findings=findings)


def audit_plan_result(result: PlanResult, user_content: str = "", *, expect_multi_unit: bool = False) -> MethodologyReport:
    return audit_orchestration_actions(
        result.actions,
        reply=result.reply or "",
        thinking=result.thinking or "",
        user_content=user_content,
        expect_multi_unit=expect_multi_unit,
    )


def assert_methodology(result: PlanResult, user_content: str = "", *, expect_multi_unit: bool = False) -> None:
    report = audit_plan_result(result, user_content, expect_multi_unit=expect_multi_unit)
    if not report.ok:
        failed = "; ".join(f"P{f.principle} {f.name}: {f.detail}" for f in report.failed())
        raise AssertionError(f"工作方式审计未通过：{failed}")
