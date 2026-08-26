package com.vibepaper.canvas.controller;

import com.vibepaper.canvas.dto.CanvasDtos;
import com.vibepaper.canvas.entity.Canvas;
import com.vibepaper.canvas.mapper.CanvasMapper;
import com.vibepaper.canvas.service.CanvasService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

/**
 * 内部接口：identity 建默认画布、agent/gallery 读画布数据、gallery 克隆导入。
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalController {
    private final CanvasService canvasService;
    private final CanvasMapper canvasMapper;

    @PostMapping("/canvases/default")
    public Map<String, Object> createDefaultCanvas(@RequestParam Long userId, @RequestParam String nickname) {
        CanvasDtos.CanvasView canvas = canvasService.createForInternal(
                new CanvasDtos.CreateCanvasRequest(nickname + " 的画布", "默认画布"), userId);
        return Map.of("canvasId", canvas.id());
    }

    @GetMapping("/canvases/{canvasId}")
    public CanvasDtos.CanvasDetail getCanvas(@PathVariable Long canvasId) {
        Canvas canvas = canvasService.getById(canvasId);
        if (canvas == null) {
            throw com.vibepaper.common.api.ApiException.notFound("画布不存在");
        }
        return canvasService.buildDetail(canvas);
    }

    /**
     * Agent 上下文摘要（缺了才查）：节点统计 / 关键词 / 有效连线 / 选中与上下游 / stale。
     */
    @GetMapping("/canvases/{canvasId}/summary")
    public Map<String, Object> getCanvasSummary(
            @PathVariable Long canvasId,
            @RequestParam(required = false) String selectedNodeIds,
            @RequestParam(defaultValue = "2") int relatedDepth) {
        List<Long> selected = List.of();
        if (selectedNodeIds != null && !selectedNodeIds.isBlank()) {
            selected = Arrays.stream(selectedNodeIds.split(","))
                    .map(String::trim)
                    .filter(s -> !s.isEmpty())
                    .map(Long::valueOf)
                    .toList();
        }
        return canvasService.buildSummary(canvasId, selected, Math.max(0, Math.min(relatedDepth, 3)));
    }

    @GetMapping("/canvases/{canvasId}/export")
    public Map<String, Object> exportInternal(@PathVariable Long canvasId) {
        Canvas canvas = canvasService.getById(canvasId);
        if (canvas == null) {
            throw com.vibepaper.common.api.ApiException.notFound("画布不存在");
        }
        return canvasService.exportInternalForOwner(canvasId);
    }

    @PostMapping("/canvases/import")
    public Map<String, Object> importInternal(@RequestBody Map<String, Object> body) {
        Object rawOwner = body.get("ownerId");
        if (rawOwner == null) {
            throw com.vibepaper.common.api.ApiException.badRequest(
                    com.vibepaper.common.api.ErrorCode.INVALID_INPUT, "ownerId 必填");
        }
        Long ownerId = rawOwner instanceof Number n ? n.longValue() : Long.parseLong(rawOwner.toString());
        Object rawJson = body.get("json");
        if (rawJson == null) {
            throw com.vibepaper.common.api.ApiException.badRequest(
                    com.vibepaper.common.api.ErrorCode.INVALID_INPUT, "json 必填");
        }
        String json = rawJson instanceof String s ? s : writeJson(rawJson);
        CanvasDtos.CanvasDetail detail = canvasService.importCanvas(json, ownerId);
        return Map.of("canvasId", detail.canvas().id(), "name", detail.canvas().name());
    }

    private String writeJson(Object obj) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    @GetMapping("/canvases/owner/{ownerId}/count")
    public Map<String, Object> canvasCount(@PathVariable Long ownerId) {
        Long count = canvasMapper.selectCount(new LambdaQueryWrapper<Canvas>().eq(Canvas::getOwnerId, ownerId));
        return Map.of("count", count);
    }
}
