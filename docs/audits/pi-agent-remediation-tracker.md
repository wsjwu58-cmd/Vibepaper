# Pi Agent 审计修复追踪器

> 基线：`docs/audits/pi-agent-secondary-development-comprehensive-review-2026-08-28.md`。
> 状态只有在对应测试命令已经执行并保留结果后才能从 `planned` 变为 `verified`。

## 状态定义

- `planned`: 已分配实现任务，尚无本轮测试证据。
- `in_progress`: 正在实现或等待阶段门禁。
- `verified`: 测试、契约和验收证据均已记录。

## 覆盖矩阵

```json
[
  {"auditId":"AGT-PI-P0-01","taskIds":[8,9],"status":"planned","evidence":["Task 8 approval-service.test.ts and Task 9 generation-action-executor.test.ts pending"]},
  {"auditId":"AGT-PI-P0-02","taskIds":[10,13,14,15],"status":"planned","evidence":["ToolManifest and tool contract tests pending"]},
  {"auditId":"AGT-PI-P0-03","taskIds":[9,15,31],"status":"planned","evidence":["Authoritative estimate and Billing contract tests pending"]},
  {"auditId":"AGT-PI-P0-04","taskIds":[5,6],"status":"planned","evidence":["Run event stream tests pending"]},
  {"auditId":"AGT-PI-P0-05","taskIds":[5,6],"status":"planned","evidence":["Server-side cancellation tests pending"]},
  {"auditId":"AGT-PI-P0-06","taskIds":[6,22],"status":"planned","evidence":["Events and Skill attach route tests pending"]},
  {"auditId":"AGT-PI-P0-07","taskIds":[7],"status":"planned","evidence":["Task terminal callback contract tests pending"]},
  {"auditId":"AGT-PI-P0-08","taskIds":[5,7],"status":"planned","evidence":["Notice consumer and outbox tests pending"]},
  {"auditId":"AGT-PI-P0-09","taskIds":[3,7],"status":"planned","evidence":["Fail-closed startup and callback auth tests pending"]},
  {"auditId":"AGT-PI-P0-10","taskIds":[4,25],"status":"planned","evidence":["Owner-scoped drama tests pending"]},
  {"auditId":"AGT-PI-P0-11","taskIds":[4,23],"status":"planned","evidence":["Canvas binding and explicit copy tests pending"]},
  {"auditId":"AGT-PI-P0-12","taskIds":[8],"status":"planned","evidence":["Concurrent atomic approval consumption test pending"]},
  {"auditId":"AGT-PI-P0-13","taskIds":[2],"status":"planned","evidence":["Versioned migration checksum tests pending"]},
  {"auditId":"AGT-PI-P0-14","taskIds":[3,35],"status":"planned","evidence":["Required Pi CI job test pending"]},
  {"auditId":"AGT-PI-P0-15","taskIds":[3],"status":"planned","evidence":["Nacos registration health tests pending"]},
  {"auditId":"AGT-PI-P1-01","taskIds":[11],"status":"planned","evidence":["Profile decision table tests pending"]},
  {"auditId":"AGT-PI-P1-02","taskIds":[18],"status":"planned","evidence":["Browser node reference acceptance pending"]},
  {"auditId":"AGT-PI-P1-03","taskIds":[12,13],"status":"planned","evidence":["Canvas context builder tests pending"]},
  {"auditId":"AGT-PI-P1-04","taskIds":[5,19],"status":"planned","evidence":["Transcript observation recovery tests pending"]},
  {"auditId":"AGT-PI-P1-05","taskIds":[20],"status":"planned","evidence":["Protected-facts compaction tests pending"]},
  {"auditId":"AGT-PI-P1-06","taskIds":[5,19],"status":"planned","evidence":["Session lease and steer concurrency tests pending"]},
  {"auditId":"AGT-PI-P1-07","taskIds":[16,17],"status":"planned","evidence":["OpenAPI and reducer contract tests pending"]},
  {"auditId":"AGT-PI-P1-08","taskIds":[6,16],"status":"planned","evidence":["Strict delta tests pending"]},
  {"auditId":"AGT-PI-P1-09","taskIds":[6,16],"status":"planned","evidence":["Failed and aborted terminal event tests pending"]},
  {"auditId":"AGT-PI-P1-10","taskIds":[6,9,31],"status":"planned","evidence":["Usage and cost reconciliation tests pending"]},
  {"auditId":"AGT-PI-P1-11","taskIds":[11,17,31],"status":"planned","evidence":["Model capability and snapshot tests pending"]},
  {"auditId":"AGT-PI-P1-12","taskIds":[21],"status":"planned","evidence":["Memory retrieval and injection tests pending"]},
  {"auditId":"AGT-PI-P1-13","taskIds":[22],"status":"planned","evidence":["Skill version/hash replay tests pending"]},
  {"auditId":"AGT-PI-P1-14","taskIds":[22],"status":"planned","evidence":["Skill governance tests pending"]},
  {"auditId":"AGT-PI-P1-15","taskIds":[4,17],"status":"planned","evidence":["Stable error code contract tests pending"]},
  {"auditId":"AGT-PI-P1-16","taskIds":[4,34],"status":"planned","evidence":["Request ID propagation tests pending"]},
  {"auditId":"AGT-PI-P1-17","taskIds":[9],"status":"planned","evidence":["Queued compensation tests pending"]},
  {"auditId":"AGT-PI-P1-18","taskIds":[3],"status":"planned","evidence":["Drama and render review route tests pending"]},
  {"auditId":"AGT-PI-P1-19","taskIds":[17],"status":"planned","evidence":["TypeBox/OpenAPI generation tests pending"]},
  {"auditId":"AGT-PI-P1-20","taskIds":[2],"status":"planned","evidence":["Database constraint migration tests pending"]},
  {"auditId":"AGT-PI-P1-21","taskIds":[2],"status":"planned","evidence":["Multi-worker Snowflake tests pending"]},
  {"auditId":"AGT-PI-P1-22","taskIds":[3],"status":"planned","evidence":["Single environment configuration tests pending"]},
  {"auditId":"AGT-PI-P1-23","taskIds":[18],"status":"planned","evidence":["Existing automated node reference regression retained"]},
  {"auditId":"AGT-PI-P2-01","taskIds":[5,6],"status":"planned","evidence":["Persistent runs, outbox and replay tests pending"]},
  {"auditId":"AGT-PI-P2-02","taskIds":[24],"status":"planned","evidence":["Plan version and rerun audit tests pending"]},
  {"auditId":"AGT-PI-P2-03","taskIds":[24,26],"status":"planned","evidence":["Dependency Ready Set and stale compiler tests pending"]},
  {"auditId":"AGT-PI-P2-04","taskIds":[25,26,27,28,30],"status":"planned","evidence":["Short-drama production chain tests pending"]},
  {"auditId":"AGT-PI-P2-05","taskIds":[29],"status":"planned","evidence":["Read-only render audit tests pending"]},
  {"auditId":"AGT-PI-P2-06","taskIds":[31],"status":"planned","evidence":["Model capability, fallback and budget tests pending"]},
  {"auditId":"AGT-PI-P2-07","taskIds":[21,32],"status":"planned","evidence":["Enterprise memory governance tests pending"]},
  {"auditId":"AGT-PI-P2-08","taskIds":[23],"status":"planned","evidence":["Session lifecycle tests pending"]},
  {"auditId":"AGT-PI-P2-09","taskIds":[6,16],"status":"planned","evidence":["Frontend reconnect and visible error tests pending"]},
  {"auditId":"AGT-PI-P2-10","taskIds":[33,34],"status":"planned","evidence":["Evaluation, trace diff and attribution tests pending"]}
]
```

## 更新规则

每次执行任务后补充：测试命令、通过数量、提交或工作区文件、人工验收结果。没有可重放的测试命令，不得标记 `verified`。
## 2026-08-29 真实实现核验

本轮源码与测试差异记录见 [pi-agent-full-implementation-gap-2026-08-29.md](./pi-agent-full-implementation-gap-2026-08-29.md)。本轮已把 RenderBatch/RenderJob 的 PostgreSQL 事实层、权威估价、确认令牌、输入哈希、逐镜 Generation 提交、终态回写和事务状态聚合接入；企业治理、线上评测、CharacterLook/供应商重试、Billing 原子批量预冻结、TTS/字幕/合成自动任务化和全栈三镜头验收仍保持未完成。
