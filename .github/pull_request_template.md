## 变更说明

<!-- 简述本次改动的内容与目的（为什么做、做了什么） -->

## 变更类型

- [ ] feat — 新功能
- [ ] fix — 缺陷修复
- [ ] refactor — 重构（无行为变化）
- [ ] perf — 性能优化
- [ ] chore — 构建 / 工程化 / 依赖
- [ ] docs — 文档
- [ ] test — 测试补充

## 关联需求 / Issue

<!-- 关联的 Spec / PRD 章节 / Issue 编号，如 PRD §5.3 BILL-01 -->

## 自检清单 (DoD — AGENTS.md §9.4)

- [ ] 规则 / 权限 / 异常路径已确认
- [ ] 接口与数据字典对齐（OpenAPI / 数据库迁移）
- [ ] 正常 / 边界 / 失败用例通过
- [ ] 涉及计费：核心分支覆盖 ≥ 90%（BILL-01~07）
- [ ] 涉及 Agent：确认令牌 / 工具白名单已校验
- [ ] 涉及画布：乐观锁 / schema_version 已处理
- [ ] 日志 / 埋点 / 审计已接入（task_id / user_id / error_code）
- [ ] 无阻塞缺陷
- [ ] 文档已同步（Spec / PRD 待确认项）

## CI 验证

- [ ] Java 服务 `mvn verify` 通过
- [ ] Python 服务 `ruff check` + `pytest` 通过
- [ ] 前端 `oxlint` + `vite build` 通过

## 测试方式

<!-- 简述如何验证本次改动 -->
