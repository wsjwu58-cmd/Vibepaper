package com.vibepaper.canvas.controller;

import com.vibepaper.canvas.dto.CanvasDtos;
import com.vibepaper.canvas.service.CanvasService;
import com.vibepaper.canvas.service.DramaAssetService;
import com.vibepaper.canvas.service.GraphService;
import com.vibepaper.common.api.PageResult;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/canvases")
@RequiredArgsConstructor
public class CanvasController {
    private final CanvasService canvasService;
    private final GraphService graphService;
    private final DramaAssetService dramaAssetService;

    @PostMapping
    public CanvasDtos.CanvasView create(@Valid @RequestBody CanvasDtos.CreateCanvasRequest req) {
        return canvasService.create(req);
    }

    @GetMapping
    public PageResult<CanvasDtos.CanvasView> list(@RequestParam(defaultValue = "1") int page,
                                                  @RequestParam(defaultValue = "20") int pageSize,
                                                  @RequestParam(required = false) String keyword) {
        return canvasService.list(page, pageSize, keyword);
    }

    @GetMapping("/{canvasId}")
    public CanvasDtos.CanvasDetail detail(@PathVariable Long canvasId) {
        return canvasService.detail(canvasId);
    }

    @PutMapping("/{canvasId}")
    public CanvasDtos.CanvasView update(@PathVariable Long canvasId,
                                        @RequestBody CanvasDtos.UpdateCanvasRequest req) {
        return canvasService.update(canvasId, req);
    }

    @DeleteMapping("/{canvasId}")
    public Map<String, String> delete(@PathVariable Long canvasId) {
        canvasService.delete(canvasId);
        return Map.of("status", "ok");
    }

    @PostMapping("/{canvasId}/save")
    public CanvasDtos.CanvasDetail save(@PathVariable Long canvasId, @RequestBody CanvasDtos.SaveCanvasRequest req) {
        return canvasService.save(canvasId, req);
    }

    @PostMapping("/{canvasId}/export")
    public Map<String, Object> export(@PathVariable Long canvasId) {
        return canvasService.export(canvasId);
    }

    @PostMapping(value = "/import", consumes = MediaType.APPLICATION_JSON_VALUE)
    public CanvasDtos.CanvasDetail importCanvas(@RequestBody String json) {
        return canvasService.importCanvas(json, null);
    }

    @GetMapping("/shared/{token}")
    public CanvasDtos.CanvasDetail viewShared(@PathVariable String token) {
        return canvasService.viewShared(token);
    }

    // ---- 节点 ----
    @PostMapping("/{canvasId}/nodes")
    public CanvasDtos.NodePayload addNode(@PathVariable Long canvasId,
                                          @Valid @RequestBody CanvasDtos.CreateNodeRequest req) {
        return graphService.addNode(canvasId, req);
    }

    @PutMapping("/{canvasId}/nodes/{nodeId}")
    public CanvasDtos.NodePayload updateNode(@PathVariable Long canvasId, @PathVariable Long nodeId,
                                             @RequestBody CanvasDtos.UpdateNodeRequest req) {
        return graphService.updateNode(canvasId, nodeId, req);
    }

    @DeleteMapping("/{canvasId}/nodes/{nodeId}")
    public Map<String, Object> deleteNode(@PathVariable Long canvasId, @PathVariable Long nodeId) {
        return graphService.deleteNode(canvasId, nodeId);
    }

    // ---- 连线 ----
    @PostMapping("/{canvasId}/edges")
    public CanvasDtos.EdgePayload addEdge(@PathVariable Long canvasId,
                                          @Valid @RequestBody CanvasDtos.CreateEdgeRequest req) {
        return graphService.addEdge(canvasId, req);
    }

    @DeleteMapping("/{canvasId}/edges/{edgeId}")
    public Map<String, String> deleteEdge(@PathVariable Long canvasId, @PathVariable Long edgeId) {
        graphService.deleteEdge(canvasId, edgeId);
        return Map.of("status", "ok");
    }

    // ---- 编组 ----
    @PostMapping("/{canvasId}/groups")
    public CanvasDtos.GroupPayload addGroup(@PathVariable Long canvasId,
                                            @RequestBody Map<String, Object> body) {
        List<Long> nodeIds = ((List<?>) body.get("nodeIds")).stream()
                .map(v -> ((Number) v).longValue()).toList();
        return graphService.addGroup(canvasId, nodeIds, (String) body.get("color"));
    }

    @PutMapping("/{canvasId}/groups/{groupId}")
    public CanvasDtos.GroupPayload updateGroup(@PathVariable Long canvasId, @PathVariable Long groupId,
                                               @RequestBody Map<String, Object> body) {
        List<Long> nodeIds = body.get("nodeIds") == null ? null
                : ((List<?>) body.get("nodeIds")).stream().map(v -> ((Number) v).longValue()).toList();
        return graphService.updateGroup(canvasId, groupId, (String) body.get("name"),
                (String) body.get("color"), (String) body.get("layout"), nodeIds);
    }

    @DeleteMapping("/{canvasId}/groups/{groupId}")
    public Map<String, String> deleteGroup(@PathVariable Long canvasId, @PathVariable Long groupId) {
        graphService.deleteGroup(canvasId, groupId);
        return Map.of("status", "ok");
    }

    // ---- 堆叠 ----
    @PostMapping("/{canvasId}/stacks")
    public CanvasDtos.StackPayload addStack(@PathVariable Long canvasId, @RequestBody Map<String, Object> body) {
        List<Long> nodeIds = ((List<?>) body.get("nodeIds")).stream()
                .map(v -> ((Number) v).longValue()).toList();
        return graphService.addStack(canvasId, nodeIds);
    }

    @PutMapping("/{canvasId}/stacks/{stackId}")
    public CanvasDtos.StackPayload updateStack(@PathVariable Long canvasId, @PathVariable Long stackId,
                                               @RequestBody Map<String, Object> body) {
        return graphService.updateStack(canvasId, stackId,
                body.get("collapsed") == null ? null : (Boolean) body.get("collapsed"));
    }

    @PostMapping("/{canvasId}/stacks/{stackId}/extract")
    public CanvasDtos.NodePayload extract(@PathVariable Long canvasId, @PathVariable Long stackId,
                                          @RequestBody Map<String, Object> body) {
        return graphService.extractFromStack(canvasId, stackId, ((Number) body.get("nodeId")).longValue());
    }

    @DeleteMapping("/{canvasId}/stacks/{stackId}")
    public Map<String, String> deleteStack(@PathVariable Long canvasId, @PathVariable Long stackId) {
        graphService.deleteStack(canvasId, stackId);
        return Map.of("status", "ok");
    }

    // ---- 短剧领域资产 ----
    @PostMapping("/{canvasId}/drama-assets")
    public CanvasDtos.DramaAssetPayload upsertDramaAsset(
            @PathVariable Long canvasId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody CanvasDtos.UpsertDramaAssetRequest req) {
        return dramaAssetService.upsert(canvasId, idempotencyKey, req);
    }

    @GetMapping("/{canvasId}/drama-assets")
    public Map<String, Object> listDramaAssets(
            @PathVariable Long canvasId,
            @RequestParam(required = false) String assetType,
            @RequestParam(required = false) String episodeId,
            @RequestParam(required = false) String sceneId,
            @RequestParam(required = false) String shotId) {
        return Map.of("items", dramaAssetService.list(canvasId, assetType, episodeId, sceneId, shotId));
    }

    // ---- 分享 ----
    @PostMapping("/{canvasId}/share")
    public CanvasDtos.CanvasDetail share(@PathVariable Long canvasId,
                                         @Valid @RequestBody CanvasDtos.ShareRequest req) {
        return canvasService.share(canvasId, req);
    }
}
