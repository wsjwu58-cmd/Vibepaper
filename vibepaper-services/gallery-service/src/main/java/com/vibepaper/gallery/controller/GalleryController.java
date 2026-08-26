package com.vibepaper.gallery.controller;

import com.vibepaper.gallery.entity.Publication;
import com.vibepaper.gallery.service.GalleryService;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.api.PageResult;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class GalleryController {
    private final GalleryService galleryService;

    @GetMapping("/api/v1/gallery/publications")
    public PageResult<Map<String, Object>> listPublic(@RequestParam(defaultValue = "1") int page,
                                                      @RequestParam(defaultValue = "20") int pageSize,
                                                      @RequestParam(required = false) String keyword) {
        return galleryService.listPublic(page, pageSize, keyword);
    }

    @PostMapping("/api/v1/publications")
    public Publication publish(@RequestBody Map<String, Object> body) {
        if (body == null || body.get("canvasId") == null) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "canvasId 必填");
        }
        List<String> resultUrls = new ArrayList<>();
        Object rawList = body.get("resultAssetUrls");
        if (rawList instanceof List<?> list) {
            for (Object item : list) {
                if (item != null) resultUrls.add(item.toString());
            }
        }
        List<String> tags = new ArrayList<>();
        Object rawTags = body.get("tags");
        if (rawTags instanceof List<?> list) {
            for (Object item : list) {
                if (item != null) tags.add(item.toString());
            }
        } else if (rawTags instanceof String s && !s.isBlank()) {
            for (String part : s.split("[,，\\s]+")) {
                if (!part.isBlank()) tags.add(part.trim());
            }
        }
        Object rawCanvasId = body.get("canvasId");
        long canvasId = rawCanvasId instanceof Number n
                ? n.longValue()
                : Long.parseLong(rawCanvasId.toString());
        return galleryService.publish(new GalleryService.PublishRequest(
                canvasId,
                body.get("title") == null ? null : body.get("title").toString(),
                body.get("description") == null ? null : body.get("description").toString(),
                tags,
                body.get("thumbnailUrl") == null ? null : body.get("thumbnailUrl").toString(),
                body.get("previewAssetUrl") == null ? null : body.get("previewAssetUrl").toString(),
                resultUrls
        ));
    }

    @GetMapping("/api/v1/gallery/publications/{id}")
    public Map<String, Object> detail(@PathVariable Long id) {
        return galleryService.detail(id);
    }

    @PostMapping("/api/v1/gallery/publications/{id}/clone")
    public Map<String, Object> clone(@PathVariable Long id) {
        return galleryService.clone(id);
    }

    @DeleteMapping("/api/v1/publications/{id}")
    public Map<String, String> deleteOwn(@PathVariable Long id) {
        galleryService.deleteOwn(id);
        return Map.of("status", "ok");
    }

    @GetMapping("/api/v1/publications/admin/list")
    public PageResult<Map<String, Object>> moderationList(@RequestParam(required = false) String status,
                                                          @RequestParam(defaultValue = "1") int page,
                                                          @RequestParam(defaultValue = "20") int pageSize) {
        return galleryService.moderationList(status, page, pageSize);
    }

    @GetMapping("/api/v1/publications/admin/stats")
    public Map<String, Long> moderationStats() {
        return Map.of(
                "pending", galleryService.countByStatus("pending"),
                "published", galleryService.countByStatus("published"),
                "rejected", galleryService.countByStatus("rejected"),
                "taken_down", galleryService.countByStatus("taken_down")
        );
    }

    @PostMapping("/api/v1/publications/admin/{id}/{action}")
    public Publication moderate(@PathVariable Long id, @PathVariable String action,
                                @RequestBody(required = false) Map<String, String> body) {
        return galleryService.moderate(id, action, body == null ? null : body.get("reason"));
    }

    @PostMapping("/api/v1/publications/admin/batch")
    public Map<String, Integer> batch(@RequestBody Map<String, Object> body) {
        List<Long> ids = ((List<?>) body.get("ids")).stream().map(v -> {
            if (v instanceof Number n) return n.longValue();
            return Long.parseLong(v.toString());
        }).toList();
        int count = galleryService.batchModerate(ids, body.get("action").toString(),
                body.get("reason") == null ? null : body.get("reason").toString());
        return Map.of("processed", count);
    }
}
