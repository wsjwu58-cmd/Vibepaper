# Pi Agent 运行手册

按 `request_id → session_id → run_id → task_id/action_id` 串联日志；先确认 run 终态和 event_seq，再检查 Canvas 版本、Billing 冻结流水及 generation 终态回调。遇到 Nacos、SSE 或供应商故障时保持 fail-closed，暂停新高风险提交，使用幂等键重放查询，不手工改账本。

发布门槛：越权为 0、重复冻结为 0、active run 不可恢复为 0；超过阈值时启用旧 Agent/只读 shadow 回滚开关，并保留审计报告与 trace。
