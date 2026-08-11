package com.vibepaper.admin.controller;

import com.vibepaper.admin.service.AdminService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 内部接口：审计记录与埋点收集（PRD §11）。
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalController {
    private final AdminService adminService;

    @PostMapping("/audit-logs")
    public Map<String, String> audit(@RequestBody Map<String, Object> body) {
        adminService.recordAudit(
                body.get("action") == null ? "unknown" : body.get("action").toString(),
                body.get("targetType") == null ? null : body.get("targetType").toString(),
                body.get("targetId") == null ? null : ((Number) body.get("targetId")).longValue(),
                body.get("before"), body.get("after"));
        return Map.of("status", "ok");
    }

    @PostMapping("/analytics-events")
    public Map<String, String> track(@RequestBody Map<String, Object> body) {
        adminService.trackEvent(body.get("eventName") == null ? "unknown" : body.get("eventName").toString(),
                body.get("payload") == null ? Map.of() : (Map<String, Object>) body.get("payload"));
        return Map.of("status", "ok");
    }
}
