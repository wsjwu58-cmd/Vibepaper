# Pi Agent Production Readiness

日期：2026-08-29

## 已落地的控制面

- Snowflake ID 使用显式 worker/datacenter 配置，启动配置在 staging/production 缺失密钥时 fail-closed。
- Agent run、事件序列、SSE cursor、取消、终态任务回调、Action/Approval、权威估价与补偿路径已有单元测试。
- 画布访问、Drama owner scope、Memory/Skill scope、审校只读权限、企业配额与敏感字段脱敏已有回归测试。
- 计划版本、依赖 Ready Set/stale、关键帧优先批处理、音频/字幕/合成 lineage、离线评测和 telemetry 基础已建立。

## 发布阻断项

生产发布前必须补齐真实 PostgreSQL/RocketMQ/Billing/Generation 集成、浏览器三镜头 E2E、进程重启恢复、SSE 断线重连、Nacos 故障注入，以及连续 7 天 1%→10%→50%→100% 灰度指标。旧 Python Agent 在 parity catalog、回滚演练和账本零重复证据完成前不得删除。

## 回滚与审计

使用只读 shadow/旧 Agent 开关回滚；以 `request_id → session_id → run_id → task_id/action_id` 查询链路。禁止手工改点数账本；确认并发、供应商降级和回调重复必须通过幂等键重放。
