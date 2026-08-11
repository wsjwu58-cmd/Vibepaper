package com.vibepaper.admin.controller;

import com.vibepaper.admin.entity.Announcement;
import com.vibepaper.admin.entity.ApiKey;
import com.vibepaper.admin.entity.AuditLog;
import com.vibepaper.admin.entity.MemberTier;
import com.vibepaper.admin.service.AdminService;
import com.vibepaper.common.api.PageResult;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class AdminController {
    private final AdminService adminService;

    // ---- 用户管理 ----
    @GetMapping("/api/v1/admin/users")
    public Map<String, Object> users(@RequestParam(required = false) String keyword,
                                     @RequestParam(required = false) String status,
                                     @RequestParam(defaultValue = "1") int page,
                                     @RequestParam(defaultValue = "20") int pageSize) {
        return adminService.listUsers(keyword, status, page, pageSize);
    }

    @GetMapping("/api/v1/admin/users/{userId}")
    public Map<String, Object> userDetail(@PathVariable Long userId) {
        return adminService.userDetail(userId);
    }

    @PutMapping("/api/v1/admin/users/{userId}/status")
    public Map<String, String> updateUserStatus(@PathVariable Long userId, @RequestBody Map<String, String> body) {
        adminService.updateUserStatus(userId, body.get("status"));
        return Map.of("status", "ok");
    }

    // ---- 交易 ----
    @GetMapping("/api/v1/admin/transactions")
    public List<Map<String, Object>> transactions(@RequestParam(required = false) String status) {
        return adminService.transactions(status);
    }

    // ---- 充值套餐 ----
    @PostMapping("/api/v1/admin/packages")
    public Map<String, Object> createPackage(@RequestBody Map<String, Object> body) {
        return adminService.createPackage(body);
    }

    @PutMapping("/api/v1/admin/packages/{packageId}")
    public Map<String, Object> updatePackage(@PathVariable Long packageId, @RequestBody Map<String, Object> body) {
        return adminService.updatePackage(packageId, body);
    }

    @DeleteMapping("/api/v1/admin/packages/{packageId}")
    public Map<String, String> deletePackage(@PathVariable Long packageId) {
        adminService.deletePackage(packageId);
        return Map.of("status", "ok");
    }

    // ---- 模型管理 ----
    @GetMapping("/api/v1/admin/models")
    public Map<String, Object> models(@RequestParam(required = false) String type) {
        return adminService.listModels(type);
    }

    @PostMapping("/api/v1/admin/models")
    public Map<String, Object> createModel(@RequestBody Map<String, Object> body) {
        return adminService.createModel(body);
    }

    @PutMapping("/api/v1/admin/models/{modelId}")
    public Map<String, Object> updateModel(@PathVariable Long modelId, @RequestBody Map<String, Object> body) {
        return adminService.updateModel(modelId, body);
    }

    @DeleteMapping("/api/v1/admin/models/{modelId}")
    public Map<String, String> deleteModel(@PathVariable Long modelId) {
        adminService.deleteModel(modelId);
        return Map.of("status", "ok");
    }

    @PutMapping("/api/v1/admin/models/{modelId}/pricing")
    public Map<String, Object> updatePricing(@PathVariable Long modelId, @RequestBody Map<String, Object> body) {
        return adminService.updatePricing(modelId, body);
    }

    // ---- 公告 ----
    @GetMapping("/api/v1/admin/announcements")
    public PageResult<Announcement> announcements(@RequestParam(required = false) String status,
                                                  @RequestParam(defaultValue = "1") int page,
                                                  @RequestParam(defaultValue = "20") int pageSize) {
        return adminService.listAnnouncements(status, page, pageSize);
    }

    @PostMapping("/api/v1/admin/announcements")
    public Announcement createAnnouncement(@RequestBody Map<String, String> body) {
        return adminService.upsertAnnouncement(null, body.get("title"), body.get("content"), body.get("status"));
    }

    @PutMapping("/api/v1/admin/announcements/{id}")
    public Announcement updateAnnouncement(@PathVariable Long id, @RequestBody Map<String, String> body) {
        return adminService.upsertAnnouncement(id, body.get("title"), body.get("content"), body.get("status"));
    }

    @DeleteMapping("/api/v1/admin/announcements/{id}")
    public Map<String, String> deleteAnnouncement(@PathVariable Long id) {
        adminService.deleteAnnouncement(id);
        return Map.of("status", "ok");
    }

    // ---- 审计 ----
    @GetMapping("/api/v1/admin/audit-logs")
    public PageResult<AuditLog> auditLogs(@RequestParam(required = false) String action,
                                          @RequestParam(required = false) Long operatorId,
                                          @RequestParam(defaultValue = "1") int page,
                                          @RequestParam(defaultValue = "20") int pageSize) {
        return adminService.auditLogs(action, operatorId, page, pageSize);
    }

    // ---- API Key ----
    @GetMapping("/api/v1/admin/api-keys")
    public List<ApiKey> apiKeys() {
        return adminService.listApiKeys();
    }

    @PostMapping("/api/v1/admin/api-keys")
    public ApiKey upsertApiKey(@RequestBody Map<String, Object> body) {
        return adminService.upsertApiKey(
                body.get("id") == null ? null : ((Number) body.get("id")).longValue(),
                body.get("name") == null ? null : body.get("name").toString(),
                body.get("provider") == null ? null : body.get("provider").toString(),
                body.get("apiKey") == null ? null : body.get("apiKey").toString(),
                body.get("baseUrl") == null ? null : body.get("baseUrl").toString(),
                body.get("rateLimit") == null ? null : ((Number) body.get("rateLimit")).intValue());
    }

    @PutMapping("/api/v1/admin/api-keys/{id}/toggle")
    public Map<String, String> toggleApiKey(@PathVariable Long id, @RequestBody Map<String, Boolean> body) {
        adminService.toggleApiKey(id, body.getOrDefault("enabled", false));
        return Map.of("status", "ok");
    }

    // ---- 会员体系（P2） ----
    @GetMapping("/api/v1/admin/member-tiers")
    public List<MemberTier> tiers() {
        return adminService.listTiers();
    }

    @PostMapping("/api/v1/admin/member-tiers")
    public MemberTier upsertTier(@RequestBody Map<String, Object> body) {
        String benefits;
        try {
            benefits = body.get("benefits") == null ? "{}"
                    : new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(body.get("benefits"));
        } catch (Exception e) {
            benefits = "{}";
        }
        return adminService.upsertTier(
                body.get("id") == null ? null : ((Number) body.get("id")).longValue(),
                body.get("name") == null ? null : body.get("name").toString(),
                body.get("level") == null ? null : ((Number) body.get("level")).intValue(),
                body.get("priceCny") == null ? null : ((Number) body.get("priceCny")).intValue(),
                benefits,
                body.get("enabled") == null ? true : (Boolean) body.get("enabled"));
    }
}
