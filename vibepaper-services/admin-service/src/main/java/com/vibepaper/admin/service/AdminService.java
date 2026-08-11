package com.vibepaper.admin.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.vibepaper.admin.entity.*;
import com.vibepaper.admin.feign.*;
import com.vibepaper.admin.mapper.*;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.api.PageResult;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * 运营后台（P1｜B-38/B-40~B-47，会员 B-39 P2）。
 * 未列出的操作默认拒绝；敏感操作二次确认 + 审计日志。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AdminService {
    private final AuditLogMapper auditLogMapper;
    private final AnnouncementMapper announcementMapper;
    private final AnnouncementReadMapper readMapper;
    private final ApiKeyMapper apiKeyMapper;
    private final MemberTierMapper tierMapper;
    private final AnalyticsEventMapper analyticsMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final IdentityAdminClient identityClient;
    private final BillingAdminClient billingClient;
    private final GenerationAdminClient generationClient;
    private final CanvasAdminClient canvasClient;

    public Map<String, Object> listUsers(String keyword, String status, int page, int pageSize) {
        requireAdmin();
        return identityClient.pageUsers(keyword, status, page, pageSize);
    }

    public Map<String, Object> userDetail(Long userId) {
        requireAdmin();
        Map<String, Object> detail = new java.util.HashMap<>(identityClient.getUser(userId));
        try {
            detail.put("ledgers", billingClient.ledgers(userId));
        } catch (Exception e) {
            detail.put("ledgers", List.of());
        }
        try {
            detail.put("canvasCount", canvasClient.canvasCount(userId).getOrDefault("count", 0));
        } catch (Exception e) {
            detail.put("canvasCount", 0);
        }
        return detail;
    }

    @Transactional
    public void updateUserStatus(Long userId, String status) {
        requireAdmin();
        if (!List.of("active", "disabled", "banned", "deleted").contains(status)) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "非法状态: " + status);
        }
        Map<String, Object> before = identityClient.getUser(userId);
        identityClient.updateStatus(userId, Map.of("status", status));
        audit("user.status.update", "user", userId, before, Map.of("status", status));
    }

    public List<Map<String, Object>> transactions(String status) {
        requireAdmin();
        return billingClient.transactions(status);
    }

    @Transactional
    public Map<String, Object> createPackage(Map<String, Object> body) {
        requireAdmin();
        Map<String, Object> created = billingClient.createPackage(body);
        audit("package.create", "recharge_package", null, null, body);
        return created;
    }

    @Transactional
    public Map<String, Object> updatePackage(Long packageId, Map<String, Object> body) {
        requireAdmin();
        Map<String, Object> updated = billingClient.updatePackage(packageId, body);
        audit("package.update", "recharge_package", packageId, null, body);
        return updated;
    }

    @Transactional
    public void deletePackage(Long packageId) {
        requireAdmin();
        billingClient.deletePackage(packageId);
        audit("package.delete", "recharge_package", packageId, null, null);
    }

    // ---- 模型管理（generation-service 数据） ----
    public Map<String, Object> listModels(String type) {
        requireAdmin();
        return generationClient.listModels(type);
    }

    @Transactional
    public Map<String, Object> createModel(Map<String, Object> body) {
        requireAdmin();
        Map<String, Object> created = generationClient.createModel(body);
        audit("model.create", "model_config", null, null, body);
        return created;
    }

    @Transactional
    public Map<String, Object> updateModel(Long modelId, Map<String, Object> body) {
        requireAdmin();
        Map<String, Object> updated = generationClient.updateModel(modelId, body);
        audit("model.update", "model_config", modelId, null, body);
        return updated;
    }

    @Transactional
    public void deleteModel(Long modelId) {
        requireAdmin();
        generationClient.deleteModel(modelId);
        audit("model.delete", "model_config", modelId, null, null);
    }

    @Transactional
    public Map<String, Object> updatePricing(Long modelId, Map<String, Object> body) {
        requireAdmin();
        Map<String, Object> updated = generationClient.updatePricing(modelId, body);
        audit("model.pricing.update", "pricing_rule", modelId, null, body);
        return updated;
    }

    // ---- 公告 ----
    public PageResult<Announcement> listAnnouncements(String status, int page, int pageSize) {
        Page<Announcement> p = announcementMapper.selectPage(new Page<>(page, pageSize),
                new LambdaQueryWrapper<Announcement>()
                        .eq(status != null && !status.isBlank(), Announcement::getStatus, status)
                        .orderByDesc(Announcement::getPublishedAt));
        return PageResult.of(p.getRecords(), p.getTotal(), page, pageSize);
    }

    public List<Map<String, Object>> userAnnouncements() {
        List<Announcement> list = announcementMapper.selectList(new LambdaQueryWrapper<Announcement>()
                .eq(Announcement::getStatus, "published").orderByDesc(Announcement::getPublishedAt));
        Long userId = RequestContext.userIdLong();
        return list.stream().map(a -> {
            AnnouncementRead read = userId == null ? null : readMapper.selectOne(new LambdaQueryWrapper<AnnouncementRead>()
                    .eq(AnnouncementRead::getUserId, userId).eq(AnnouncementRead::getAnnouncementId, a.getId()));
            return Map.<String, Object>of(
                    "id", a.getId(), "title", a.getTitle(), "content", a.getContent(),
                    "publishedAt", a.getPublishedAt() == null ? null : a.getPublishedAt().toString(),
                    "read", read != null);
        }).toList();
    }

    @Transactional
    public void markAnnouncementRead(Long announcementId) {
        Long userId = RequestContext.userIdLong();
        AnnouncementRead existing = readMapper.selectOne(new LambdaQueryWrapper<AnnouncementRead>()
                .eq(AnnouncementRead::getUserId, userId).eq(AnnouncementRead::getAnnouncementId, announcementId));
        if (existing == null) {
            AnnouncementRead read = new AnnouncementRead();
            read.setUserId(userId);
            read.setAnnouncementId(announcementId);
            read.setReadAt(OffsetDateTime.now());
            readMapper.insert(read);
        }
    }

    @Transactional
    public Announcement upsertAnnouncement(Long id, String title, String content, String status) {
        requireAdmin();
        Announcement announcement;
        if (id == null) {
            announcement = new Announcement();
            announcement.setId(idGenerator.nextId());
            announcement.setCreatedAt(OffsetDateTime.now());
        } else {
            announcement = announcementMapper.selectById(id);
            if (announcement == null) {
                throw ApiException.notFound("公告不存在");
            }
        }
        announcement.setTitle(title);
        announcement.setContent(content);
        announcement.setStatus(status == null ? "draft" : status);
        if ("published".equals(status)) {
            announcement.setPublishedAt(OffsetDateTime.now());
        }
        if (id == null) {
            announcementMapper.insert(announcement);
        } else {
            announcementMapper.updateById(announcement);
        }
        audit("announcement.upsert", "announcement", announcement.getId(), null, Map.of("title", title, "status", status));
        return announcement;
    }

    @Transactional
    public void deleteAnnouncement(Long id) {
        requireAdmin();
        announcementMapper.deleteById(id);
        audit("announcement.delete", "announcement", id, null, null);
    }

    // ---- 审计日志 ----
    public PageResult<AuditLog> auditLogs(String action, Long operatorId, int page, int pageSize) {
        requireAdmin();
        Page<AuditLog> p = auditLogMapper.selectPage(new Page<>(page, pageSize),
                new LambdaQueryWrapper<AuditLog>()
                        .eq(action != null && !action.isBlank(), AuditLog::getAction, action)
                        .eq(operatorId != null, AuditLog::getOperatorId, operatorId)
                        .orderByDesc(AuditLog::getCreatedAt));
        return PageResult.of(p.getRecords(), p.getTotal(), page, pageSize);
    }

    @Transactional
    public void recordAudit(String action, String targetType, Long targetId, Object before, Object after) {
        audit(action, targetType, targetId, before, after);
    }

    public void audit(String action, String targetType, Long targetId, Object before, Object after) {
        try {
            AuditLog logEntry = new AuditLog();
            logEntry.setId(idGenerator.nextId());
            logEntry.setOperatorId(RequestContext.userIdLong());
            logEntry.setAction(action);
            logEntry.setTargetType(targetType);
            logEntry.setTargetId(targetId);
            logEntry.setBeforeValue(writeJson(before));
            logEntry.setAfterValue(writeJson(after));
            logEntry.setIp(RequestContext.requestId() == null ? "" : RequestContext.requestId());
            logEntry.setRequestId(RequestContext.requestId());
            logEntry.setCreatedAt(OffsetDateTime.now());
            auditLogMapper.insert(logEntry);
        } catch (Exception e) {
            log.warn("audit record failed: {}", e.getMessage());
        }
    }

    // ---- 第三方 API Key（B-42） ----
    public List<ApiKey> listApiKeys() {
        requireAdmin();
        return apiKeyMapper.selectList(new LambdaQueryWrapper<ApiKey>().orderByDesc(ApiKey::getCreatedAt));
    }

    @Transactional
    public ApiKey upsertApiKey(Long id, String name, String provider, String apiKey, String baseUrl, Integer rateLimit) {
        requireAdmin();
        ApiKey key;
        if (id == null) {
            key = new ApiKey();
            key.setId(idGenerator.nextId());
            key.setCreatedAt(OffsetDateTime.now());
        } else {
            key = apiKeyMapper.selectById(id);
            if (key == null) {
                throw ApiException.notFound("API Key 不存在");
            }
        }
        key.setName(name);
        key.setProvider(provider);
        if (apiKey != null && !apiKey.isBlank()) {
            key.setKeyCipher(java.util.Base64.getEncoder().encodeToString(apiKey.getBytes()));
        }
        key.setBaseUrl(baseUrl);
        key.setRateLimit(rateLimit == null ? 60 : rateLimit);
        key.setEnabled(key.getEnabled() == null ? true : key.getEnabled());
        if (id == null) {
            apiKeyMapper.insert(key);
        } else {
            apiKeyMapper.updateById(key);
        }
        audit("api_key.upsert", "api_key", key.getId(), null, Map.of("name", name, "provider", provider));
        return key;
    }

    @Transactional
    public void toggleApiKey(Long id, Boolean enabled) {
        requireAdmin();
        ApiKey key = apiKeyMapper.selectById(id);
        if (key == null) {
            throw ApiException.notFound("API Key 不存在");
        }
        key.setEnabled(enabled);
        apiKeyMapper.updateById(key);
        audit("api_key.toggle", "api_key", id, null, Map.of("enabled", enabled));
    }

    // ---- 会员体系（P2｜B-39） ----
    public List<MemberTier> listTiers() {
        requireAdmin();
        return tierMapper.selectList(new LambdaQueryWrapper<MemberTier>().orderByAsc(MemberTier::getLevel));
    }

    @Transactional
    public MemberTier upsertTier(Long id, String name, Integer level, Integer priceCny, String benefits, Boolean enabled) {
        requireAdmin();
        MemberTier tier;
        if (id == null) {
            tier = new MemberTier();
            tier.setId(idGenerator.nextId());
        } else {
            tier = tierMapper.selectById(id);
            if (tier == null) {
                throw ApiException.notFound("会员等级不存在");
            }
        }
        tier.setName(name);
        tier.setLevel(level);
        tier.setPriceCny(priceCny);
        tier.setBenefits(benefits);
        tier.setEnabled(enabled);
        if (id == null) {
            tierMapper.insert(tier);
        } else {
            tierMapper.updateById(tier);
        }
        audit("member_tier.upsert", "member_tier", tier.getId(), null, Map.of("name", name, "level", level));
        return tier;
    }

    // ---- 埋点（PRD §11） ----
    @Transactional
    public void trackEvent(String eventName, Map<String, Object> payload) {
        AnalyticsEvent event = new AnalyticsEvent();
        event.setId(idGenerator.nextId());
        event.setEventName(eventName);
        event.setPayload(writeJson(payload));
        event.setCreatedAt(OffsetDateTime.now());
        analyticsMapper.insert(event);
    }

    private void requireAdmin() {
        if (!RequestContext.isAdmin()) {
            throw ApiException.forbidden("仅运营管理员可执行该操作");
        }
    }

    private String writeJson(Object obj) {
        if (obj == null) {
            return null;
        }
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            return "{}";
        }
    }
}
