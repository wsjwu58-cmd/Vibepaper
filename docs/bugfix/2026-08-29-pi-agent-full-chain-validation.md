# Pi Agent 全链路验证问题与修复记录（2026-08-29）

## 结论

评测基础设施、数据库迁移、Skill 加载、SSE 事件证据和幂等链路已修复并通过回归。按用户提供的 Agnes 配置进行真实调用后：资产只读用例通过；商品视觉曾真实生成一张 Agnes 图片并在 Generation 侧取得 `succeeded` 终态；最新商品视觉长链在首轮 Agnes 文本阶段超过有限等待窗口，按外部阻断处理，不能把整条长链计为通过。关键帧长链也未取得终态。没有伪造媒体、任务或点数成功结果。

本轮使用 `agnes-2.5-flash`（Agent 文本）、`agnes-image-2.1-flash`（图片）和 `agnes-video-2.5-flash`（视频），统一走 Agnes 官方 API Hub；密钥只写入被忽略的本地 `.env`，未进入代码、文档、日志或证据。

## 测试证据

- 评测命令：`cd E:\VibePaperProject\pi-main; npm run eval --workspace=@vibepaper/pi-agent-service -- evals/cases/<case>.json`
- 覆盖结果：6 类 modality、9 个 operation、21 个 Skill、51 轮；`coverage_gaps` 全为空。
- 运行结果：旧证据目录中的历史结果仍包含 `blocked_external`，不能覆盖本轮真实运行；本轮已采信的资产用例为 `passed`，商品视觉和关键帧用例在真实长响应阶段中止。其余用例按未取得新的正向终态处理。
- 证据校验：`pwsh -File scripts/e2e/check-evidence.ps1 -Root output/evals/2026-08-29` → `cases=16,status=ok`。
- 证据目录：[output/evals/2026-08-29](../../output/evals/2026-08-29)。每个 case 有 `result.json`、`events.ndjson`、`media-probe.json`；因没有媒体产物，探针状态为 `not_run`。
- Agent 回归：47 个测试文件、121 个测试通过；构建通过。
- Generation 回归：11 个测试通过；模型目录显示 Agnes 文本/图片/视频三个启用模型。
- Web 回归：3 个测试文件、6 个测试通过；生产构建通过。
- 浏览器证据：已启动 `5173`，通过真实注册流程进入画布管理和画布编辑器，保存并视觉检查了 3 张截图：[browser evidence](../../pi-main/packages/vibepaper-agent-service/output/evals/2026-08-29-browser-evidence/screenshots/)。截图展示真实的画布管理、Agent 面板及 Agnes 文本模型选择；未用伪造截图替代媒体结果。
- generation-service 健康检查：`8090/health` 返回 200。
- 历史在线幂等检查：首次和重复提交均返回 200，SSE 内容完全一致，复用同一 `runId`；该记录的终态为 `MODEL_UNAVAILABLE`，仅作为无模型配置时的回归证据，不代表本轮 Agnes 结果。

## 已定位并修复的问题

### 1. Eval 入口不是计划要求的真实客户端

原入口只有旧 JSON loader，没有多轮 Schema、公开 Agent API 客户端、确认、SSE resume、脱敏和媒体探针；计划中的 workspace 相对路径在 npm workspace cwd 下还会重复拼接。

修复：新增 `eval-schema.ts`、`eval-client.ts`、`evidence-writer.ts`、`media-probe.ts`、路径兼容的 `case-loader.ts`，替换 `run-evals.ts`，并把覆盖缺口作为显式输出。运行器现在依据声明的 event/task/node/media/lineage/error 断言判定，不会因接口返回 200 就误报通过。

### 2. Windows 下迁移目录解析错误

`import.meta.url.pathname` 在 Windows 下会产生 `/E:/...` 形式路径，导致 Agent 启动时找不到 migrations。

修复：使用 `fileURLToPath(new URL(...))`，并增加迁移路径回归测试。

### 3. 旧数据库与新 Agent schema 不兼容

旧 `schema_migrations` 没有 `filename` 默认值，历史 baseline checksum 与当前文件不同；旧 `user_memories`、`agent_actions`、`agent_sessions` 缺少当前运行查询需要的列。结果是请求已经创建 `queued` run、写入用户消息，却在 Skill/Memory 上下文阶段返回 PostgreSQL 参数/列错误。

修复：

- 对已识别的历史 baseline checksum 做精确兼容，不放宽其他迁移校验。
- 增加集中式 `003_legacy_schema_reconcile.sql`，补齐历史表字段；同时为现有 `004` 迁移补充幂等列保护。
- 将 `ensureBuiltinSkills` 的参数全部显式 cast（`bigint`/`varchar`/`text`），解决 PostgreSQL `$2` 类型推断冲突。
- 新增 Skill bootstrap 回归测试；修复后完整评测不再出现 500 或 `INTERNAL_ERROR`。

### 4. SSE 证据和追踪链不完整

原 `events.ndjson` 只写 resume 事件，turn 内的 `run_failed`、工具和确认事件会丢失；原始 SSE 流也没有透传 request ID。

修复：turn 事件与 resume 事件统一写入并脱敏；消息和事件 SSE 均透传 `X-Request-Id`，证据现在可以关联 `requestId → sessionId → runId → event/task`。

### 5. 垂直领域 Skill 覆盖不完整

计划 Appendix B 要求 21 个创作 Skill，而仓库原 manifest 只有 14 个创作 Skill 加 2 个画布 Skill。补充了产品视觉、产品喷绘广告、反重力产品广告、电商经营、潮流视觉 PV、实景纸刊、界面设计，并将 manifest 生成器和 Skill 合同测试更新为 21 个创作 Skill + 2 个核心 Skill。

### 6. 评测夹具首轮画布版本错误

评测客户端创建 Canvas 后把首轮 `canvasVersion` 默认成 `0`，而 Canvas 创建后的实际版本是 `1`；正常节点写入被乐观锁拒绝，Agent 又将 409 过度归类成 `CANVAS_UNAVAILABLE`。

修复：评测夹具读取 Canvas 创建响应的版本并保存到会话；运行时 `get_canvas_summary` 同步嵌套的权威版本。Canvas 网关对 403/404/409 保留 `PERMISSION_DENIED`/`NOT_FOUND`/`VERSION_CONFLICT`。

### 7. Canvas 运行 JAR 落后于源码

真实 Agent 的 `get_node_detail` 曾命中旧 JAR，导致源码已有的 GET 节点详情路由返回错误。重新打包并重启 Canvas 服务后，直接 GET 节点详情返回 200。

### 8. 旧 Agent 数据库缺少审批费用列

真实图片提交时，旧库 `agent_actions` 缺少 `estimated_cost`，审批持久化失败。新增 `013_agent_action_cost_reconcile.sql`，并修复独立 `migrate.ts` 的 Windows 路径解析；迁移命令现已实际执行成功。

### 9. 评测器没有解析嵌套工具输出

节点和 lineage 信息位于工具结果的 JSON 文本中，断言器只读取事件顶层字段，导致审计用例误报 `node:video`。现已递归解析嵌套 JSON，并让审计夹具支持种子节点和选中节点。

### 10. 长链编排未收敛

真实 Agnes 文本响应在商品视觉、关键帧等多轮链路中持续产生增量事件但未达到 `run_completed`，期间曾出现模型重复尝试更新/删除节点和字符串化参数。工具 Schema 已拒绝错误参数，本轮不将未终态链路归因于 Agnes 图片/视频服务成功。

修复：评测客户端现在在确认后等待任务终态，再进入下一轮；写画布工具先等待写入完成再回读权威 `canvasVersion`；`submit_generation` 从服务端权威节点补齐缺失 prompt；Generation 终态回调同时接受 camelCase 与 snake_case 字段。上述修复均有失败测试和回归测试。

### 11. 旧 `agent_actions.status` 长度不足

历史数据库列为 `VARCHAR(16)`，确认动作写入 `awaiting_approval` 时会在持久化阶段失败。新增 `014_agent_action_status_reconcile.sql` 扩展为 `VARCHAR(32)`，已在真实 Agent 数据库执行并核验迁移记录；对应迁移测试已通过。

### 12. 浏览器证据缺失

此前前端 `5173` 未启动，浏览器场景无法执行。现已启动 Vite，使用固定浏览器会话完成一次性评测账号注册、画布管理、编辑器和 Agent 面板检查，并保存真实 PNG；账号密码未写入仓库、截图或文档。

## 未能完成的真实正向链路

- 虽已配置 Agnes key，最新长链在首轮文本响应阶段无响应；因此仍不能宣称商品视觉长链、关键帧链、TTS、字幕和最终 15 镜短剧成片已通过。已有商品视觉单任务 `219414789640818688` 与 `219415820311334912` 在 Generation 侧均为 `succeeded`，输出为真实 JPEG，provider/model 为 `agnes-image` / `agnes-image-2.1-flash`；两笔任务均核验到 freeze→settle→unfreeze_settle 账本闭环且当前 frozen points 为 0，但它们不等价于完整长链通过。
- 浏览器页面已执行并有真实截图，但该浏览器会话使用新注册评测账号，未冒充为已完成的媒体任务会话。
- Nacos `8848` 与 RocketMQ `9876` 未监听；Java 服务进程已启动，但 `/health` 不是现有 Java 服务的有效资源路径，不能据此宣称全栈健康。
- 最近长链还受到 Agnes 指定时间窗口调用次数/响应时延限制；评估器在有限窗口后主动中止，不通过填充假数据或伪造媒体来“修复”。

## 继续验证条件

在本机启动前端和 Nacos/RocketMQ，并为长链增加单轮工具预算/超时与失败后版本回读后，重新执行上述评测命令；重点先看 `core-product-visual-001`、`director-stage-001`、`vertical-short-drama-full-episode-001`，然后再执行安全/恢复和 Skill 用例。完整短剧只有在 15 个 4 秒视频、逐镜音频/字幕和最终 9:16 Compose 均有真实终态时才算通过。
