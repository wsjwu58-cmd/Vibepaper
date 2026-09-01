# VibePaper

个人独立开发的 **AI 原生节点化无限画布** 创作平台。

以无限画布为容器、以节点承载文本 / 图片 / 视频 / 音频，通过连线建立引用关系，由 Agent 驱动编排，并用点数计费闭环支撑创作全流程：

**创意 → 生成 → 编辑 → 组合 → 导出**

> 本仓库为个人学习与实践项目，持续迭代中。目标是对齐并实现 vibepaper-ai.com 的已确认产品能力与关键交互（不含商标、受版权素材与私有算法）。

---

## 分支说明

| 分支 | 定位 |
|------|------|
| `dev` | 默认分支；集成最新的 Node.js + Pi Agent Core 版本及全栈开发改动 |
| `main` | Python 版本分支；保留 `agent-service` 与 `generation-service` 的 Python 运行基线 |

---

## 功能概览

| 能力 | 说明 |
|------|------|
| 无限画布 | 平移缩放、节点/连线 CRUD、乐观锁自动保存、导入导出 |
| 多模态生成 | 文本 / 图片 / 视频 / 音频节点，任务状态机与消耗预览 |
| Agent 编排 | 基于 Pi Agent Core 的 SSE 流式对话、工具白名单、高风险操作确认令牌 |
| Agent 控制面 | 会话 / Run 生命周期、事件流恢复、取消、任务终态回调、权限与审计 |
| 短剧工作流 | 故事圣经、单集、分镜、关键帧、视频、音频 / 字幕与合成的依赖编排 |
| 点数计费 | 冻结 → 结算 / 解冻，流水只追加，超时自动解冻 |
| 素材库 | 上传、拖入画布、引用检查 |
| 管理空间 | 画布管理、任务历史、订阅/点数、个人中心 |
| 扩展（P1+） | 编组/堆叠、企业中心、创意广场、运营后台等 |

更完整的需求与排期见 `docs/`。

---

## 技术架构

```
vibepaper-web (React + TypeScript + Vite + @xyflow/react)
        │ REST / SSE
        ▼
vibepaper-gateway (Spring Cloud Gateway)
        │
   ┌────┴─────────────────────────────┐
   │ Java 21 + Spring Boot            │ Python 3.12 + FastAPI
   │ identity · canvas · asset        │ generation-service
   │ billing · enterprise · gallery   │
   │ admin               Node.js + TypeScript + Fastify
   │                     agent-service（Pi Agent Core）
   └────┬─────────────────────────────┘
   PostgreSQL · Redis · Nacos · RocketMQ · MinIO（可本地文件替代）
```

| 模块 | 技术 | 职责 |
|------|------|------|
| `vibepaper-web` | React 19 · Vite · Zustand · TanStack Query · Tailwind | 前端单应用 |
| `vibepaper-services` | Java 21 · Spring Boot 3 · Spring Cloud Gateway | 业务微服务 + 网关 |
| `generation-service` | FastAPI · 任务状态机 · Mock/真实 Provider | 生成与模型目录 |
| `agent-service` | Node.js 22.19+ · TypeScript · Fastify · Pi Agent Core · SSE | Agent 会话、短剧领域编排与受控工具 |
| `deploy/` | PowerShell / Docker Compose | 本地启停与基础设施 |

---

## 仓库结构

```
docs/                  # PRD、技术概要、功能清单、Spec、执行计划
vibepaper-services/    # Java 微服务（common + gateway + 业务服务）
generation-service/    # Python 生成服务
pi-main/                # 锁定的 Pi 上游源码与 VibePaper Agent 工作区
  packages/vibepaper-agent-service/  # Node.js + Pi 的 Agent 服务
vibepaper-web/         # React 前端
deploy/                # 一键启停与 compose
AGENTS.md              # Agent / 协作者工程契约
```

---

## 快速开始

### 环境要求

- JDK 21、Maven
- Python 3.12、[uv](https://github.com/astral-sh/uv) 或 venv（仅 generation-service）
- Node.js 22.19+、npm、pnpm
- PostgreSQL、Redis；可选 Nacos、RocketMQ、MinIO

本地数据库、中间件地址与密码请通过环境变量或本地配置文件覆盖，**不要**把真实凭据提交进仓库。可参考各服务下的 `.env.example`（如有）。

### 后端（Java）

```powershell
cd vibepaper-services
mvn -s settings-project.xml install -DskipTests
```

### Python 生成服务

```powershell
cd generation-service
# 创建 venv、安装依赖后：
python scripts\init_db.py
```

### Pi Agent 服务

`agent-service` 已迁移为 Pi Agent Core 的 Node.js 服务。Pi 上游源码位于 `pi-main/`，VibePaper 的二次开发代码只位于 `pi-main/packages/vibepaper-agent-service/`，不修改上游的 `packages/agent`、`packages/ai` 或 `packages/coding-agent`。

```powershell
cd pi-main
npm install --ignore-scripts
npm run build --workspace=@vibepaper/pi-agent-service

Copy-Item packages\vibepaper-agent-service\.env.example packages\vibepaper-agent-service\.env
# 在 .env 中填入 VIBEPAPER_DATABASE_URL、VIBEPAPER_REDIS_URL 与 Agnes API Key
npm run start --workspace=@vibepaper/pi-agent-service
```

服务默认监听 `8091`。模型配置沿用原有 Agnes 兼容接口：优先使用 `VIBEPAPER_LLM_*`，未设置时回退到 `VIBEPAPER_AGNES_*`；默认模型为 `agnes-2.5-flash`。

短剧垂直 Agent 把角色、世界观、剧集索引和镜头链条作为可读写的持久化事实，按“故事圣经 → 单集 → 分镜 → 提示词 → 关键帧 → 视频 → 拼接”分层执行。人物镜头缺少角色参考图、关键帧未就绪即提交视频等情况由服务端工具约束拒绝，不能仅靠提示词规避。

Skill 仅向会话注入索引；正文通过 `load_skill` 按需加载。内置画布 Skill 与用户可启停的动态 Skill 均遵守用户本次指令、单次卡片覆写、全局偏好、Skill 内容、模型默认值的优先级。

### 一键启停（本机已装好中间件时）

```powershell
.\deploy\start-all.ps1
.\deploy\stop-all.ps1
```

启动后可运行全栈健康检查；脚本会检查前端、Java 服务、生成服务、Agent、PostgreSQL、Redis、Nacos 和 RocketMQ 的连通性：

```powershell
.\deploy\verify-all.ps1
.\deploy\verify-all.ps1 -Json
```

### 前端

```powershell
cd vibepaper-web
pnpm install
pnpm dev   # http://localhost:5173
```

---

## 核心设计要点

**计费闭环**：提交任务前校验可用点数并冻结；成功按实际费用结算；失败 / 取消 / 超时全额解冻；流水表只追加。

**Agent 安全**：仅可调用工具白名单；删除、高花费、改模型等操作需确认令牌（绑定用户、画布版本与操作摘要）。

**画布并发**：`canvas.version` 乐观锁；V1 不支持多人实时同编。

**Agent 全链路**：Agent 通过受控工具读写画布和短剧领域事实，事件使用序号与 SSE cursor 支持恢复；生成提交、确认、取消、终态回写和点数对账均保留可审计链路。涉及高风险写入时，服务端拒绝绕过确认令牌的请求。

**验证状态**：单元测试、契约测试、前端构建和离线评测已纳入本轮回归；真实 PostgreSQL / RocketMQ / Billing / Generation 集成、SSE 断线重连、进程重启恢复、Nacos 故障注入及灰度发布仍是生产发布前门槛。验证设计与结果见下方文档索引。

详情见 `docs/VibePaper产品需求文档新版.md` 与 `docs/技术概要设计方案.md`。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [AGENTS.md](./AGENTS.md) | 术语、技术栈硬约束、编码准则 |
| [产品需求文档](./docs/VibePaper产品需求文档新版.md) | 产品契约 |
| [技术概要设计](./docs/技术概要设计方案.md) | 微服务与技术选型 |
| [工程 Spec](./docs/specs/V1.0-engineering-spec.md) | V1.0 工程说明 |
| [执行计划](./docs/plans/execution-plan.md) | 分阶段排期 |
| [Pi 全量迁移设计](./docs/specs/pi-agent-full-replacement-design.md) | Node.js + Pi Agent Core 的迁移基线 |
| [短剧 Agent 方向](./docs/specs/pi-vertical-short-drama-agent-direction.md) | 短剧状态层、镜头流水线、审校与调度 |
| [全链路验证计划](./docs/plans/2026-08-29-pi-agent-full-chain-validation-plan.md) | Agent A-D 全链路验收、证据和门禁 |
| [实现差异审计](./docs/audits/pi-agent-full-implementation-gap-2026-08-29.md) | Agent 实现与契约的差异记录 |
| [修复追踪器](./docs/audits/pi-agent-remediation-tracker.md) | 审计项、测试证据与验证状态 |
| [评测协议](./docs/evals/pi-agent-evaluation-protocol.md) | 离线 / 线上评测字段与硬失败规则 |
| [运行手册](./docs/operations/pi-agent-runbook.md) | 运行排障、链路追踪与回滚门槛 |

评测运行输出默认写入 `output/evals/`，其中可能包含截图和媒体探针结果；这些运行产物不作为源码提交，提交前应只保留可复现的用例、脚本和报告。

---

## 声明

- 作者个人开发与学习用途，接口、架构与功能仍可能大幅调整。
- 与任何商业产品无官方从属关系；复刻范围仅限已公开确认的产品能力与交互思路。
- 欢迎 Issue / Discussion；PR 请尽量保持小而清晰。

---

## License

[MIT](./LICENSE) © 2026 ShiJie Wu
