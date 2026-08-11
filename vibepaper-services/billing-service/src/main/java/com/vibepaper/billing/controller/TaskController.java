package com.vibepaper.billing.controller;

import com.vibepaper.billing.service.PointService;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 任务提交与取消（计费侧）。
 */
@RestController
@RequestMapping("/api/v1/tasks")
@RequiredArgsConstructor
public class TaskController {
    private final PointService pointService;

    @PostMapping
    @SuppressWarnings("unchecked")
    public Map<String, Object> create(@RequestHeader("Idempotency-Key") @NotBlank String idempotencyKey,
                                      @RequestBody Map<String, Object> body) {
        PointService.FreezeRequest req = new PointService.FreezeRequest(
                asLong(body.get("userId")),
                asLong(body.get("nodeId")),
                asLong(body.get("canvasId")),
                body.get("modelType") == null ? "text" : body.get("modelType").toString(),
                body.get("modelParams") == null ? Map.of() : (Map<String, Object>) body.get("modelParams"),
                asInt(body.get("estimatedCost")),
                body.get("source") == null ? "user" : body.get("source").toString(),
                idempotencyKey);
        return pointService.freeze(req);
    }

    @PostMapping("/{taskId}/cancel")
    public Map<String, String> cancel(@PathVariable Long taskId) {
        pointService.cancel(taskId);
        return Map.of("status", "cancelled");
    }

    /** 前端雪花 ID 常以字符串传输，避免强转 Number 失败。 */
    private static Long asLong(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number n) {
            return n.longValue();
        }
        String s = value.toString().trim();
        if (s.isEmpty()) {
            return null;
        }
        return Long.parseLong(s);
    }

    private static int asInt(Object value) {
        if (value == null) {
            throw new IllegalArgumentException("estimatedCost is required");
        }
        if (value instanceof Number n) {
            return n.intValue();
        }
        return Integer.parseInt(value.toString().trim());
    }
}
