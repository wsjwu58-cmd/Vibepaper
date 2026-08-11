# VibePaper

个人独立开发的 **AI 原生节点化无限画布** 创作平台。

以无限画布为容器、以节点承载文本 / 图片 / 视频 / 音频，通过连线建立引用关系，由 Agent 驱动编排，并用点数计费闭环支撑创作全流程：

**创意 → 生成 → 编辑 → 组合 → 导出**

> 本仓库为个人学习与实践项目，持续迭代中。目标是对齐并实现 vibepaper-ai.com 的已确认产品能力与关键交互（不含商标、受版权素材与私有算法）。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| 无限画布 | 平移缩放、节点/连线 CRUD、乐观锁自动保存、导入导出 |
| 多模态生成 | 文本 / 图片 / 视频 / 音频节点，任务状态机与消耗预览 |
| Agent 编排 | SSE 流式对话、工具白名单、高风险操作确认令牌 |
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
   │ billing · enterprise · gallery   │ agent-service
   │ admin                            │
   └────┬─────────────────────────────┘
   PostgreSQL · Redis · Nacos · RocketMQ · MinIO（可本地文件替代）
```

| 模块 | 技术 | 职责 |
|------|------|------|
| `vibepaper-web` | React 19 · Vite · Zustand · TanStack Query · Tailwind | 前端单应用 |
| `vibepaper-services` | Java 21 · Spring Boot 3 · Spring Cloud Gateway | 业务微服务 + 网关 |
| `generation-service` | FastAPI · 任务状态机 · Mock/真实 Provider | 生成与模型目录 |
| `agent-service` | FastAPI · LangGraph · SSE | Agent 会话与工具 |
| `deploy/` | PowerShell / Docker Compose | 本地启停与基础设施 |

---

## 仓库结构

```
docs/                  # PRD、技术概要、功能清单、Spec、执行计划
vibepaper-services/    # Java 微服务（common + gateway + 业务服务）
generation-service/    # Python 生成服务
agent-service/         # Python Agent 服务
vibepaper-web/         # React 前端
deploy/                # 一键启停与 compose
AGENTS.md              # Agent / 协作者工程契约
```

---

## 快速开始

### 环境要求

- JDK 21、Maven
- Python 3.12、[uv](https://github.com/astral-sh/uv) 或 venv
- Node.js 20+、pnpm
- PostgreSQL、Redis；可选 Nacos、RocketMQ、MinIO

本地数据库、中间件地址与密码请通过环境变量或本地配置文件覆盖，**不要**把真实凭据提交进仓库。可参考各服务下的 `.env.example`（如有）。

### 后端（Java）

```powershell
cd vibepaper-services
mvn -s settings-project.xml install -DskipTests
```

### Python 服务

```powershell
cd generation-service
# 创建 venv、安装依赖后：
python scripts\init_db.py

cd ..\agent-service
python scripts\init_db.py
```

### 一键启停（本机已装好中间件时）

```powershell
.\deploy\start-all.ps1
.\deploy\stop-all.ps1
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

---

## 声明

- 作者个人开发与学习用途，接口、架构与功能仍可能大幅调整。
- 与任何商业产品无官方从属关系；复刻范围仅限已公开确认的产品能力与交互思路。
- 欢迎 Issue / Discussion；PR 请尽量保持小而清晰。

---

## License

[MIT](./LICENSE) © 2026 ShiJie Wu
