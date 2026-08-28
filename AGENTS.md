# VibePaper — Agent 开发规范

> 本文件是 Cursor / 自动化 Agent 的工程契约入口。  
> 权威文档：`docs/VibePaper产品需求文档新版.md`（产品契约）· `docs/技术概要设计方案.md`（技术架构）· `docs/VibePaper 产品功能清单(1).md`（功能枚举）  
> Spec 与排期：`docs/specs/V1.0-engineering-spec.md` · `docs/plans/execution-plan.md`  
> **冲突裁决**：范围与优先级以执行计划 / PRD §4.3 为准；架构与技术选型以技术概要为准；契约细节（状态机/权限/埋点）以 PRD 为准。

---

## 1. 产品一句话

VibePaper 是 AI 原生**节点化无限画布**创作平台：文本/图片/视频/音频以节点表达，连线建立引用，Agent 驱动编排，点数计费闭环支撑个人与企业。

目标：复刻 vibepaper-ai.com 的已确认功能与关键交互（不含商标、受版权素材、私有算法）。

---

## 2. 术语（强制唯一）

| 标准术语 | 英文 | 禁止混用 |
|---------|------|----------|
| 画布 | Canvas | 工作区、白板、项目、空间 |
| 节点 | Node | 模块、组件（UI 可称「卡片」，接口一律「节点」） |
| 连线 | Edge | 连接、箭头、管道 |
| 任务 | Task | 作业、请求（「生成」是动作，「任务」是实体） |
| 点数 | Points | 积分、代币、Token（Token 专指 LLM） |
| 冻结点数 | Frozen Points | 预扣、锁定、占用 |
| 素材 | Asset | 资源、文件、媒体 |
| 会话 | Session | 聊天（UI 可称「对话」） |
| Skill | Skill | 技能包、提示词模板 |
| 企业 | Enterprise | 团队、组织、公司 |
| 管理空间 | Workspace Hub | 不得与「画布」混用 |

完整定义见 PRD §1。

---

## 3. 技术栈硬约束

### 3.1 架构形态

- **微服务**：业务模块 Java；生成模块 Python；Agent 模块 Node.js + TypeScript（基于 Pi Agent Core）。
- **禁止**跨服务直连对方数据库；只能经 REST / RocketMQ。
- **禁止**服务间循环依赖。
- 各服务独立 PostgreSQL 库；全局 ID 使用 **Snowflake**（若与 PRD UUIDv4 冲突，以本规范 + 技术概要为准，并回写 PRD）。

### 3.2 服务与语言

| 服务 | 语言 | 职责摘要 |
|------|------|----------|
| `identity-service` | Java 21 + Spring Boot 3.x | 注册登录 JWT 会话偏好 |
| `canvas-service` | Java | 画布/节点/连线/DSL |
| `asset-service` | Java | 素材元数据、预签名、引用 |
| `billing-service` | Java | 账户冻结结算充值流水 |
| `enterprise-service` | Java | 企业成员邀请分配 |
| `gallery-service` | Java | 发布审核搜索克隆 |
| `admin-service` | Java | 运营后台审计 |
| `generation-service` | Python 3.12 + FastAPI | 模型目录、任务状态机、ComfyUI/供应商 |
| `agent-service` | Node.js 22.19+ + TypeScript + Fastify + Pi Agent Core | Agent 会话、Pi 编排、工具、记忆 |
| `vibepaper-gateway` | Java + Spring Cloud Gateway | 路由鉴权限流 CORS |
| `vibepaper-web` | React + TS + Vite + pnpm | 单前端应用 |

基础设施：Nacos · RocketMQ · Redis 7 · MinIO · PostgreSQL · XXL-JOB ·（Seata 仅备选）。

### 3.3 前端强制选型

React + TypeScript · Vite · `@xyflow/react` · Zustand（画布本地）· TanStack Query（服务端）· Tailwind · Radix · Lucide · React Router · React Hook Form + Zod。

目录约定：`src/app` · `src/features/{canvas,nodes,agent,assets,...}` · `src/api/generated`（OpenAPI 生成）。

### 3.4 后端分层

**Java**：`controller → service → mapper`；Controller 只接 DTO/返 VO；`@Transactional` 仅 Service；事务内禁止 Feign/发 MQ（用 Outbox）。

**Python（generation-service）**：`router → application → domain → infrastructure`；Pydantic Schema 与 ORM 分离；domain 不依赖 FastAPI/SQLAlchemy/Celery。

**Node（agent-service）**：`server → application → domain → pi/tools/infrastructure`；Pi 与 domain 不依赖 Fastify、数据库、MQ 或供应商 SDK；副作用只能通过受控 Tool Gateway 触发。

---

## 4. API 与数据契约

- 前缀：`/api/v1`；资源复数名词。
- 写接口（任务提交、充值回调、点数操作）强制 `Idempotency-Key`。
- 错误体：`{ code, message, details, request_id, retryable }`。
- 时间 ISO 8601 UTC；**点数一律 int**，禁止小数。
- OpenAPI：Java SpringDoc / Python FastAPI → `openapi-typescript` → 前端类型。
- 网关透传：`X-User-Id` · `X-User-Role` · `X-Enterprise-Id`。

稳定错误码（节选）：`INSUFFICIENT_POINTS` · `MODEL_TIMEOUT` · `MODEL_UNAVAILABLE` · `CONTENT_BLOCKED` · `INVALID_INPUT` · `FREEZE_EXPIRED` · `VERSION_CONFLICT` · `PERMISSION_DENIED`。

---

## 5. 计费硬规则（资金安全）

实现时必须对齐 PRD §5.3 / BILL-01~07：

1. `available_points = balance - frozen_points`。
2. 提交时 `available_points ≥ estimated_cost` 才冻结并建 `queued` 任务。
3. **5 分钟**内未进入 `running` → `expired` + 全额解冻。
4. 成功按 `actual_cost` 结算（V1.0 默认 `actual_cost = estimated_cost`）；失败/无效 → 全额解冻不扣费。
5. `point_ledgers` **只追加**；`UNIQUE(task_id, ledger_type)`。
6. 账户扣费：`SELECT ... FOR UPDATE` + 幂等键；跨服务优先 RocketMQ 事务消息 + Outbox。
7. 企业成员：默认不自动借企业池（除非开启共享池）。

任务状态机：`idle → queued → running → succeeded | failed | cancelled | expired`（另有 `settlement_error`）。

---

## 6. Agent 安全规则

- 只能调用**工具白名单**，禁止生成 SQL / 直连 Repository / 直接改画布 JSON。
- 高风险操作须**确认令牌**（绑定 `user_id` + `canvas_id` + `canvas_version` + 操作摘要哈希 + 过期）；画布版本变化则令牌失效。
- 确认阈值（PRD §5.2.1）：`estimated_cost ≥ 1`（提交生成）、参数变化 ≥30%、切换模型、批量创建 >20、覆盖已有输出 → 必须确认。写画布（创建/连线/布局/改配置/删除节点）免确认，执行后回显。
- 只读工具可直出；低风险写操作可直接执行并回显。

---

## 7. 画布与并发

- 画布保存：`canvas.version` **乐观锁**；冲突拒绝覆盖，提示刷新。
- V1.0 **不支持**多人实时编辑同一画布；不做 WebSocket 协作。
- 增量补丁防抖 300–500ms；最终操作立即落盘。
- 导入/导出 JSON 必须带 `schema_version`；不兼容则拒绝。

---

## 8. 优先级与范围

| 优先级 | 交付焦点 |
|--------|----------|
| **P0 / MVP** | 认证、画布 CRUD、节点/连线、文/图/音/视频生成、素材库基础、Agent 对话与确认、计费冻结结算、订阅/点数菜单、任务历史、个人中心（**不含**运营后台） |
| **P1** | 编组/堆叠、图/视频加工与 Seedance、合成/导演台、Skill/会话史、分享、签到/邀请/公告、创意广场、企业中心、运营后台 |
| **P2** | 记忆系统（短+长）、后台会员体系 |

浏览器：Chrome/Edge 100+ 全功能；Safari 16+ 基础创作；Firefox / 移动端 `<768px` **不在 V1.0**。桌面 ≥1280px。

---

## 9. 编码与提交流程

### 9.1 分支

Git Flow：`main` · `dev` · `feature/*`；PR 尽量 < 400 行。

### 9.2 规范工具

| 端 | 工具 |
|----|------|
| Java | Checkstyle + SpotBugs · Maven · Flyway |
| Python | Ruff + mypy · uv · Alembic |
| 前端 | ESLint + Prettier · Vitest + Playwright |

### 9.3 CI 门禁顺序

规范检查 → 单元测试（计费核心分支覆盖 ≥90%）→ 迁移测试 → OpenAPI 破坏性变更检测 → 集成测试 → E2E Smoke → 构建镜像。

### 9.4 DoD（单项需求完成定义）

规则/权限/异常已确认 · 接口与数据字典对齐 · 正常/边界/失败用例通过 · 对应 AC 通过 · 日志/埋点/审计已接 · 无阻塞缺陷 · 文档已更新。

---

## 10. Agent 改代码时的行为准则

1. **先读后写**：改计费/任务前必读 PRD §5.3 与技术概要 §9；改画布前读 §6.1 与前端性能策略。
2. **最小改动**：不做无关重构；不擅自扩 P1/P2 范围进 P0 分支。
3. **契约优先**：新增字段必须能在数据字典 / OpenAPI 找到依据；点数、状态枚举不得自创同义词。
4. **安全默认**：权限未列出的操作默认拒绝；敏感操作二次确认；密钥不进普通日志。
5. **可观测**：涉及任务/点数的路径必须带 `task_id` / `user_id` / `error_code` / 费用字段。
6. **文档同步**：行为变更时同步更新 Spec / PRD 待确认项，禁止静默改契约。

---

## 11. 关键路径速查

```
docs/VibePaper产品需求文档新版.md     # PRD 工程契约
docs/技术概要设计方案.md               # 微服务与技术栈
docs/VibePaper 产品功能清单(1).md     # 功能枚举
docs/specs/V1.0-engineering-spec.md   # 本轮工程 Spec
docs/plans/execution-plan.md          # 分阶段执行计划
```
