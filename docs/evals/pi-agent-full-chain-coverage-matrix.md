# Pi Agent 全链路覆盖矩阵（2026-08-29）

证据根目录：[output/evals/2026-08-29](../../output/evals/2026-08-29)。

| 维度 | 结果 | 说明 |
| --- | --- | --- |
| 用例 | 16 个 | 现有基础用例、核心多模态、Skill、并发幂等、供应商故障 |
| 自然语言轮次 | 51 轮 | 每个用例至少 2 轮 |
| modality | 6/6 | text、image、video、audio、compose、director |
| operation | 9 类 | img2img、keyframe、clip_video、extract_frame、upscale_image、upscale_video、outpaint_image、mux_audio、compose_videos |
| Skill | 21/21 | Appendix B 的 21 个创作 Skill 均出现在用例元数据和覆盖输出中 |
| Agnes 模型配置 | 已加载 | `agnes-2.5-flash`、`agnes-image-2.1-flash`、`agnes-video-2.5-flash`；密钥未写入仓库 |
| 真实正向用例 | 部分完成 | `asset-assistant-001` 已通过；商品视觉曾取得真实 Agnes 图片任务 `succeeded`，但完整长链最新重试被 Agnes 文本阶段外部阻断；关键帧长链未取得终态 |
| 确认/任务/媒体 | 部分完成 | 商品视觉单任务已核验确认后任务、真实 JPEG、provider/model 和任务终态；完整长链、视频、ffprobe、点数全链路仍不能宣称通过 |
| 故障/恢复 | 已覆盖边界 | 单元/集成回归覆盖错误码、幂等和权限；真实供应商故障与点数全链仍未取得终态 |
| 浏览器证据 | 已执行 | `5173` 已启动；真实注册、画布管理、编辑器与 Agent 面板截图见 `output/evals/2026-08-29-browser-evidence/screenshots/` |

最终运行器的元数据覆盖仍包含 6 类 modality、9 类 operation、21 个 Skill，`coverage_gaps` 为空；这表示测试设计覆盖完整，不表示业务执行成功。旧证据目录中的历史 `blocked_external` 结果已与本轮真实运行区分，不能混合作为最终通过结论。浏览器截图证明前端入口可用，但不替代媒体任务终态证据。
