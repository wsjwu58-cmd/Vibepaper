package com.vibepaper.gallery.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.api.PageResult;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import com.vibepaper.gallery.entity.CanvasSnapshot;
import com.vibepaper.gallery.entity.ModerationRecord;
import com.vibepaper.gallery.entity.Publication;
import com.vibepaper.gallery.feign.CanvasInternalClient;
import com.vibepaper.gallery.feign.IdentityInternalClient;
import com.vibepaper.gallery.mapper.CanvasSnapshotMapper;
import com.vibepaper.gallery.mapper.ModerationRecordMapper;
import com.vibepaper.gallery.mapper.PublicationMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 创意广场（P1｜F-24/B-24）：先审后发；发布即快照，原画布修改不影响已发布内容。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class GalleryService {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final int MAX_TAGS = 10;

    private final PublicationMapper publicationMapper;
    private final CanvasSnapshotMapper snapshotMapper;
    private final ModerationRecordMapper moderationMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final CanvasInternalClient canvasClient;
    private final IdentityInternalClient identityClient;

    public record PublishRequest(
            Long canvasId,
            String title,
            String description,
            List<String> tags,
            String thumbnailUrl,
            String previewAssetUrl,
            List<String> resultAssetUrls
    ) {}

    @Transactional
    public Publication publish(PublishRequest req) {
        Long userId = RequestContext.userIdLong();
        if (req == null || req.canvasId() == null) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "canvasId 必填");
        }
        String title = req.title() == null ? "" : req.title().trim();
        if (title.isBlank()) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "项目名字必填");
        }
        String thumbnailUrl = blankToNull(req.thumbnailUrl());
        if (thumbnailUrl == null) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "封面必填");
        }
        List<String> resultUrls = normalizeUrls(req.resultAssetUrls());
        String previewAssetUrl = blankToNull(req.previewAssetUrl());
        if (previewAssetUrl == null && !resultUrls.isEmpty()) {
            previewAssetUrl = resultUrls.get(0);
        }
        if (previewAssetUrl == null) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "结果文件必填");
        }
        if (resultUrls.isEmpty()) {
            resultUrls = List.of(previewAssetUrl);
        }
        List<String> tags = normalizeTags(req.tags());

        Map<String, Object> export;
        try {
            export = canvasClient.exportCanvas(req.canvasId());
        } catch (Exception e) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "无法获取画布数据: " + e.getMessage());
        }

        Publication pub = new Publication();
        pub.setId(idGenerator.nextId());
        pub.setCanvasId(req.canvasId());
        pub.setOwnerId(userId);
        pub.setTitle(title);
        pub.setDescription(blankToNull(req.description()));
        pub.setTags(writeJson(tags));
        pub.setStatus("pending");
        pub.setThumbnailUrl(thumbnailUrl);
        pub.setPreviewAssetUrl(previewAssetUrl);
        pub.setResultAssetUrls(writeJson(resultUrls));
        pub.setViewCount(0L);
        pub.setCreatedAt(OffsetDateTime.now());
        publicationMapper.insert(pub);

        CanvasSnapshot snapshot = new CanvasSnapshot();
        snapshot.setId(idGenerator.nextId());
        snapshot.setPublicationId(pub.getId());
        snapshot.setCanvasId(req.canvasId());
        snapshot.setPayload(writeJson(export));
        snapshot.setCreatedAt(OffsetDateTime.now());
        snapshotMapper.insert(snapshot);
        log.info("publication submitted id={} canvas={} user={}", pub.getId(), req.canvasId(), userId);
        return pub;
    }

    public PageResult<Map<String, Object>> listPublic(int page, int pageSize, String keyword) {
        Page<Publication> p = publicationMapper.selectPage(new Page<>(page, pageSize),
                new LambdaQueryWrapper<Publication>()
                        .eq(Publication::getStatus, "published")
                        .and(keyword != null && !keyword.isBlank(), w -> w
                                .like(Publication::getTitle, keyword)
                                .or()
                                .like(Publication::getDescription, keyword)
                                .or()
                                .like(Publication::getTags, keyword))
                        .orderByDesc(Publication::getPublishedAt));
        return PageResult.of(p.getRecords().stream().map(this::toView).toList(), p.getTotal(), page, pageSize);
    }

    @Transactional
    public Map<String, Object> detail(Long publicationId) {
        Publication pub = publicationMapper.selectById(publicationId);
        if (pub == null) {
            throw ApiException.notFound("作品不存在");
        }
        if (!"published".equals(pub.getStatus())) {
            Long userId = RequestContext.userIdLong();
            if (userId == null || !pub.getOwnerId().equals(userId)) {
                if (!RequestContext.isAdmin()) {
                    throw ApiException.forbidden("该作品未公开");
                }
            }
        } else {
            long views = pub.getViewCount() == null ? 0L : pub.getViewCount();
            pub.setViewCount(views + 1);
            publicationMapper.updateById(pub);
        }
        CanvasSnapshot snapshot = snapshotMapper.selectOne(new LambdaQueryWrapper<CanvasSnapshot>()
                .eq(CanvasSnapshot::getPublicationId, publicationId));
        Map<String, Object> view = new HashMap<>(toView(pub));
        if (snapshot != null) {
            view.put("snapshot", parse(snapshot.getPayload()));
            try {
                @SuppressWarnings("unchecked")
                Map<String, Object> snap = (Map<String, Object>) view.get("snapshot");
                Object nodes = snap == null ? null : snap.get("nodes");
                view.put("nodeCount", nodes instanceof List<?> list ? list.size() : 0);
            } catch (Exception ignored) {
                view.put("nodeCount", 0);
            }
        }
        return view;
    }

    @Transactional
    public Map<String, Object> clone(Long publicationId) {
        Long userId = RequestContext.userIdLong();
        Publication pub = publicationMapper.selectById(publicationId);
        if (pub == null || !"published".equals(pub.getStatus())) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "仅可克隆已发布作品");
        }
        CanvasSnapshot snapshot = snapshotMapper.selectOne(new LambdaQueryWrapper<CanvasSnapshot>()
                .eq(CanvasSnapshot::getPublicationId, publicationId));
        if (snapshot == null) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "作品快照不存在");
        }
        Map<String, Object> result = canvasClient.importCanvas(Map.of("ownerId", userId, "json", snapshot.getPayload()));
        log.info("publication cloned pub={} user={} newCanvas={}", publicationId, userId, result.get("canvasId"));
        return result;
    }

    @Transactional
    public void deleteOwn(Long publicationId) {
        Long userId = RequestContext.userIdLong();
        Publication pub = publicationMapper.selectById(publicationId);
        if (pub == null) {
            throw ApiException.notFound("作品不存在");
        }
        if (!pub.getOwnerId().equals(userId)) {
            throw ApiException.forbidden("只能删除自己的作品");
        }
        publicationMapper.deleteById(publicationId);
    }

    public PageResult<Map<String, Object>> moderationList(String status, int page, int pageSize) {
        Page<Publication> p = publicationMapper.selectPage(new Page<>(page, pageSize),
                new LambdaQueryWrapper<Publication>()
                        .eq(status != null && !status.isBlank(), Publication::getStatus, status)
                        .orderByAsc(Publication::getCreatedAt));
        return PageResult.of(p.getRecords().stream().map(this::toView).toList(), p.getTotal(), page, pageSize);
    }

    public long countByStatus(String status) {
        return publicationMapper.selectCount(new LambdaQueryWrapper<Publication>()
                .eq(status != null && !status.isBlank(), Publication::getStatus, status));
    }

    @Transactional
    public Publication moderate(Long publicationId, String action, String reason) {
        if (!RequestContext.isAdmin()) {
            throw ApiException.forbidden("仅运营管理员可审核");
        }
        Publication pub = publicationMapper.selectById(publicationId);
        if (pub == null) {
            throw ApiException.notFound("作品不存在");
        }
        switch (action) {
            case "approve" -> {
                pub.setStatus("published");
                pub.setPublishedAt(OffsetDateTime.now());
                pub.setRejectedReason(null);
            }
            case "reject" -> {
                if (reason == null || reason.isBlank()) {
                    throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "驳回必须填写原因");
                }
                pub.setStatus("rejected");
                pub.setRejectedReason(reason.trim());
            }
            case "take_down" -> {
                if (reason == null || reason.isBlank()) {
                    throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "下架必须填写原因");
                }
                pub.setStatus("taken_down");
                pub.setRejectedReason(reason.trim());
            }
            default -> throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "审核动作必须是 approve/reject/take_down");
        }
        publicationMapper.updateById(pub);
        ModerationRecord record = new ModerationRecord();
        record.setId(idGenerator.nextId());
        record.setPublicationId(publicationId);
        record.setOperatorId(RequestContext.userIdLong());
        record.setAction(action);
        record.setReason(reason);
        record.setCreatedAt(OffsetDateTime.now());
        moderationMapper.insert(record);
        log.info("moderation pub={} action={} operator={}", publicationId, action, RequestContext.userIdLong());
        return pub;
    }

    @Transactional
    public int batchModerate(List<Long> ids, String action, String reason) {
        int count = 0;
        for (Long id : ids) {
            try {
                moderate(id, action, reason);
                count++;
            } catch (Exception e) {
                log.warn("batch moderate skip pub={}: {}", id, e.getMessage());
            }
        }
        return count;
    }

    private Map<String, Object> toView(Publication pub) {
        Map<String, Object> view = new HashMap<>();
        // 显式字符串，避免前端 Number/JSON 精度丢失 Snowflake
        view.put("id", String.valueOf(pub.getId()));
        view.put("canvasId", String.valueOf(pub.getCanvasId()));
        view.put("ownerId", String.valueOf(pub.getOwnerId()));
        view.put("title", pub.getTitle());
        view.put("description", pub.getDescription());
        view.put("tags", parseUrlList(pub.getTags()));
        view.put("status", pub.getStatus());
        view.put("thumbnailUrl", pub.getThumbnailUrl());
        view.put("previewAssetUrl", pub.getPreviewAssetUrl());
        view.put("resultAssetUrls", parseUrlList(pub.getResultAssetUrls()));
        view.put("viewCount", pub.getViewCount() == null ? 0 : pub.getViewCount());
        view.put("rejectedReason", pub.getRejectedReason());
        view.put("publishedAt", pub.getPublishedAt() == null ? null : pub.getPublishedAt().toString());
        view.put("createdAt", pub.getCreatedAt() == null ? null : pub.getCreatedAt().toString());
        try {
            Map<String, Object> user = identityClient.getUser(pub.getOwnerId());
            view.put("authorName", user.get("nickname"));
            view.put("authorAvatar", user.get("avatarUrl"));
        } catch (Exception e) {
            view.put("authorName", "创作者");
        }
        return view;
    }

    private List<String> normalizeTags(List<String> tags) {
        List<String> out = new ArrayList<>();
        if (tags == null) return out;
        for (String t : tags) {
            String v = blankToNull(t);
            if (v != null && !out.contains(v)) {
                out.add(v);
                if (out.size() >= MAX_TAGS) break;
            }
        }
        return out;
    }

    private List<String> normalizeUrls(List<String> urls) {
        List<String> out = new ArrayList<>();
        if (urls == null) return out;
        for (String u : urls) {
            String t = blankToNull(u);
            if (t != null) out.add(t);
        }
        return out;
    }

    private String blankToNull(String s) {
        if (s == null) return null;
        String t = s.trim();
        return t.isEmpty() ? null : t;
    }

    private List<String> parseUrlList(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            @SuppressWarnings("unchecked")
            List<String> list = MAPPER.readValue(json, List.class);
            return list == null ? List.of() : list;
        } catch (Exception e) {
            return List.of();
        }
    }

    private Map<String, Object> parse(String json) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> map = MAPPER.readValue(json, Map.class);
            return map;
        } catch (Exception e) {
            return Map.of();
        }
    }

    private String writeJson(Object obj) {
        try {
            return MAPPER.writeValueAsString(obj);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
