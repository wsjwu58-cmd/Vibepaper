package com.vibepaper.canvas.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;
import java.util.Map;

public final class CanvasDtos {
    private CanvasDtos() {
    }

    public record CreateCanvasRequest(@NotBlank String name, String description) {
    }

    public record UpdateCanvasRequest(String name, String description, String thumbnailUrl) {
    }

    public record NodePayload(@NotNull Long id, String type, Double x, Double y, Double width, Double height,
                              Map<String, Object> params, String status, Long currentOutputId,
                              Long groupId, Long stackId, String creativeType, Boolean stale,
                              String modelRef, String prompt, Map<String, Object> output, String execStatus) {
    }

    public record EdgePayload(@NotNull Long id, @NotNull Long sourceNodeId, String sourcePort,
                              @NotNull Long targetNodeId, String targetPort, Boolean valid,
                              String dependencyType) {
    }

    public record GroupPayload(@NotNull Long id, String name, String color, String layout, List<Long> nodeIds) {
    }

    public record StackPayload(@NotNull Long id, Boolean collapsed, List<Long> nodeIds) {
    }

    public record SaveCanvasRequest(@NotNull Integer version, List<NodePayload> nodes,
                                    List<EdgePayload> edges, List<GroupPayload> groups,
                                    List<StackPayload> stacks) {
    }

    public record CreateNodeRequest(@NotBlank String type, Double x, Double y, Double width, Double height,
                                    Map<String, Object> params, String creativeType,
                                    String modelRef, String prompt) {
    }

    public record UpdateNodeRequest(Double x, Double y, Double width, Double height,
                                    Map<String, Object> params, String status, Long currentOutputId,
                                    Long groupId, Long stackId, String creativeType, Boolean stale,
                                    String modelRef, String prompt, Map<String, Object> output, String execStatus) {
    }

    public record CreateEdgeRequest(@NotNull Long sourceNodeId, String sourcePort,
                                    @NotNull Long targetNodeId, String targetPort,
                                    String dependencyType) {
    }

    public record ShareRequest(@NotBlank String visibility) {
    }

    public record CanvasView(Long id, Long ownerId, String name, String description, String schemaVersion,
                             Integer version, String thumbnailUrl, String visibility, String shareToken,
                             String createdAt, String updatedAt) {
    }

    public record CanvasDetail(CanvasView canvas, List<NodePayload> nodes, List<EdgePayload> edges,
                               List<GroupPayload> groups, List<StackPayload> stacks) {
    }

    public record ExportDocument(String schemaVersion, CanvasView canvas, List<NodePayload> nodes,
                                 List<EdgePayload> edges, List<GroupPayload> groups, List<StackPayload> stacks) {
    }
}
