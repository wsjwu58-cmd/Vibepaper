package com.vibepaper.canvas.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.vibepaper.canvas.domain.EdgeRules;
import com.vibepaper.canvas.dto.CanvasDtos;
import com.vibepaper.canvas.entity.*;
import com.vibepaper.canvas.mapper.*;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 节点/连线/编组/堆叠操作（PRD §6.1–§6.3，含删除影响检查）。
 */
@Service
@RequiredArgsConstructor
public class GraphService {
    private final CanvasService canvasService;
    private final CanvasNodeMapper nodeMapper;
    private final CanvasEdgeMapper edgeMapper;
    private final CanvasGroupMapper groupMapper;
    private final CanvasStackMapper stackMapper;
    private final CanvasGraphCommandMapper graphCommandMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final ObjectMapper objectMapper;

    public CanvasDtos.NodePayload getNode(Long canvasId, Long nodeId) {
        canvasService.requireOwned(canvasId);
        return canvasService.toNodePayload(requireNode(canvasId, nodeId));
    }

    @Transactional
    public CanvasDtos.NodePayload addNode(Long canvasId, CanvasDtos.CreateNodeRequest req, String idempotencyKey) {
        canvasService.requireOwned(canvasId);
        CanvasDtos.NodePayload replay = replay(idempotencyKey, canvasId, "create_nodes", CanvasDtos.NodePayload.class);
        if (replay != null) return replay;
        canvasService.assertAndAdvanceVersion(canvasId, req.expectedVersion());
        if (!EdgeRules.isValidNodeType(req.type())) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "非法节点类型: " + req.type());
        }
        CanvasNode node = new CanvasNode();
        node.setId(idGenerator.nextId());
        node.setCanvasId(canvasId);
        node.setNodeType(req.type());
        node.setPositionX(req.x() == null ? 120 : req.x());
        node.setPositionY(req.y() == null ? 120 : req.y());
        node.setWidth(req.width() == null ? 280 : req.width());
        node.setHeight(req.height() == null ? 220 : req.height());
        node.setParams(req.params() == null ? "{}" : writeJson(req.params()));
        node.setStatus("idle");
        node.setExecStatus("idle");
        node.setCreativeType(req.creativeType());
        node.setModelRef(req.modelRef());
        node.setPrompt(req.prompt() != null ? req.prompt() : extractPrompt(req.params()));
        syncParamsFromNorm(node);
        node.setStale(false);
        node.setDeleted(false);
        node.setCreatedAt(OffsetDateTime.now());
        node.setUpdatedAt(OffsetDateTime.now());
        nodeMapper.insert(node);
        CanvasDtos.NodePayload result = canvasService.toNodePayload(node);
        remember(canvasId, idempotencyKey, "create_nodes", result);
        return result;
    }

    @Transactional
    public CanvasDtos.NodePayload updateNode(Long canvasId, Long nodeId, CanvasDtos.UpdateNodeRequest req, String idempotencyKey) {
        canvasService.requireOwned(canvasId);
        CanvasDtos.NodePayload replay = replay(idempotencyKey, canvasId, "update_node_config", CanvasDtos.NodePayload.class);
        if (replay != null) return replay;
        canvasService.assertAndAdvanceVersion(canvasId, req.expectedVersion());
        CanvasNode node = requireNode(canvasId, nodeId);
        if (req.x() != null) {
            node.setPositionX(req.x());
        }
        if (req.y() != null) {
            node.setPositionY(req.y());
        }
        if (req.width() != null) {
            node.setWidth(req.width());
        }
        if (req.height() != null) {
            node.setHeight(req.height());
        }
        boolean contentChanged = false;
        if (req.params() != null) {
            node.setParams(writeJson(req.params()));
            contentChanged = true;
        }
        if (req.status() != null) {
            node.setStatus(req.status());
        }
        if (req.currentOutputId() != null) {
            node.setCurrentOutputId(req.currentOutputId());
        }
        if (req.groupId() != null) {
            node.setGroupId(req.groupId());
        }
        if (req.stackId() != null) {
            node.setStackId(req.stackId());
        }
        if (req.creativeType() != null) {
            node.setCreativeType(req.creativeType());
            contentChanged = true;
        }
        if (req.stale() != null) {
            node.setStale(req.stale());
        }
        if (req.modelRef() != null) {
            node.setModelRef(req.modelRef());
            contentChanged = true;
        }
        if (req.prompt() != null) {
            node.setPrompt(req.prompt());
            contentChanged = true;
        }
        if (req.output() != null) {
            node.setOutput(writeJson(req.output()));
            contentChanged = true;
        }
        if (req.execStatus() != null) {
            node.setExecStatus(req.execStatus());
            if (List.of("queued", "running", "succeeded", "failed", "cancelled", "expired").contains(req.execStatus())) {
                node.setStatus(req.execStatus());
            }
        }
        syncParamsFromNorm(node);
        // 节点内容更新后清除自身 stale，并沿 input 边传播下游 stale
        if (contentChanged) {
            node.setStale(false);
        }
        node.setUpdatedAt(OffsetDateTime.now());
        nodeMapper.updateById(node);
        if (contentChanged) {
            canvasService.markDownstreamStale(canvasId, nodeId);
        }
        CanvasDtos.NodePayload result = canvasService.toNodePayload(node);
        remember(canvasId, idempotencyKey, "update_node_config", result);
        return result;
    }

    @Transactional
    public Map<String, Object> deleteNode(Long canvasId, Long nodeId, Integer expectedVersion, String idempotencyKey) {
        canvasService.requireOwned(canvasId);
        Map<String, Object> replay = replayMap(idempotencyKey, canvasId, "delete_nodes");
        if (replay != null) return replay;
        canvasService.assertAndAdvanceVersion(canvasId, expectedVersion);
        CanvasNode node = requireNode(canvasId, nodeId);
        List<CanvasEdge> connected = edgeMapper.selectList(new LambdaQueryWrapper<CanvasEdge>()
                .eq(CanvasEdge::getCanvasId, canvasId)
                .and(w -> w.eq(CanvasEdge::getSourceNodeId, nodeId).or().eq(CanvasEdge::getTargetNodeId, nodeId)));
        List<Long> downstreamIds = connected.stream().filter(e -> e.getSourceNodeId().equals(nodeId))
                .map(CanvasEdge::getTargetNodeId).toList();
        List<CanvasNode> downstream = downstreamIds.isEmpty() ? List.of()
                : nodeMapper.selectList(new LambdaQueryWrapper<CanvasNode>()
                        .eq(CanvasNode::getCanvasId, canvasId)
                        .in(CanvasNode::getId, downstreamIds));
        Map<String, Object> impact = new HashMap<>();
        impact.put("connectedEdges", connected.stream().map(CanvasEdge::getId).toList());
        impact.put("downstreamNodes", downstream.stream().map(n -> Map.of(
                "id", n.getId(), "type", n.getNodeType(), "name", nodeName(n))).toList());
        nodeMapper.deleteById(nodeId);
        for (CanvasEdge edge : connected) {
            edgeMapper.deleteById(edge.getId());
        }
        impact.put("deletedNodeId", nodeId);
        remember(canvasId, idempotencyKey, "delete_nodes", impact);
        return impact;
    }

    @Transactional
    public CanvasDtos.EdgePayload addEdge(Long canvasId, CanvasDtos.CreateEdgeRequest req, String idempotencyKey) {
        canvasService.requireOwned(canvasId);
        CanvasDtos.EdgePayload replay = replay(idempotencyKey, canvasId, "connect_nodes", CanvasDtos.EdgePayload.class);
        if (replay != null) return replay;
        if (req.sourceNodeId().equals(req.targetNodeId())) {
            throw ApiException.badRequest(ErrorCode.EDGE_INVALID, "禁止自连接");
        }
        CanvasEdge existing = edgeMapper.selectOne(new LambdaQueryWrapper<CanvasEdge>()
                .eq(CanvasEdge::getCanvasId, canvasId)
                .eq(CanvasEdge::getSourceNodeId, req.sourceNodeId())
                .eq(CanvasEdge::getTargetNodeId, req.targetNodeId()));
        if (existing != null) {
            CanvasDtos.EdgePayload result = canvasService.toEdgePayload(existing);
            remember(canvasId, idempotencyKey, "connect_nodes", result);
            return result;
        }
        canvasService.assertAndAdvanceVersion(canvasId, req.expectedVersion());
        CanvasNode source = requireNode(canvasId, req.sourceNodeId());
        CanvasNode target = requireNode(canvasId, req.targetNodeId());
        boolean compatible = EdgeRules.isCompatible(source.getNodeType(), target.getNodeType());
        if (!compatible) {
            throw ApiException.badRequest(ErrorCode.EDGE_INVALID,
                    "连线不兼容：" + source.getNodeType() + " 不能作为 " + target.getNodeType() + " 的上游");
        }
        CanvasEdge edge = new CanvasEdge();
        edge.setId(idGenerator.nextId());
        edge.setCanvasId(canvasId);
        edge.setSourceNodeId(req.sourceNodeId());
        edge.setSourcePort(req.sourcePort() == null ? "output" : req.sourcePort());
        edge.setTargetNodeId(req.targetNodeId());
        edge.setTargetPort(req.targetPort() == null ? "input" : req.targetPort());
        edge.setValid(true);
        String dep = req.dependencyType() == null ? "reference" : req.dependencyType();
        if (!java.util.Set.of("reference", "input", "control").contains(dep)) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "dependencyType 必须是 reference/input/control");
        }
        edge.setDependencyType(dep);
        edge.setDeleted(false);
        edge.setCreatedAt(OffsetDateTime.now());
        edge.setUpdatedAt(OffsetDateTime.now());
        edgeMapper.insert(edge);
        CanvasDtos.EdgePayload result = canvasService.toEdgePayload(edge);
        remember(canvasId, idempotencyKey, "connect_nodes", result);
        return result;
    }

    @Transactional
    public void deleteEdge(Long canvasId, Long edgeId) {
        canvasService.requireOwned(canvasId);
        CanvasEdge edge = edgeMapper.selectById(edgeId);
        if (edge == null || !edge.getCanvasId().equals(canvasId)) {
            throw ApiException.notFound("连线不存在");
        }
        edgeMapper.deleteById(edgeId);
    }

    @Transactional
    public CanvasDtos.GroupPayload addGroup(Long canvasId, List<Long> nodeIds, String color) {
        canvasService.requireOwned(canvasId);
        if (nodeIds == null || nodeIds.size() < 2) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "编组至少需要 2 个节点");
        }
        CanvasGroup group = new CanvasGroup();
        group.setId(idGenerator.nextId());
        group.setCanvasId(canvasId);
        group.setName("编组");
        group.setColor(color == null ? "#8b5cf6" : color);
        group.setLayout("free");
        group.setNodeIds(nodeIds);
        group.setDeleted(false);
        group.setCreatedAt(OffsetDateTime.now());
        group.setUpdatedAt(OffsetDateTime.now());
        groupMapper.insert(group);
        nodeIds.forEach(id -> {
            CanvasNode n = requireNode(canvasId, id);
            n.setGroupId(group.getId());
            nodeMapper.updateById(n);
        });
        return canvasService.toGroupPayload(group);
    }

    @Transactional
    public CanvasDtos.GroupPayload updateGroup(Long canvasId, Long groupId, String name, String color, String layout,
                                               List<Long> nodeIds) {
        canvasService.requireOwned(canvasId);
        CanvasGroup group = requireGroup(canvasId, groupId);
        if (name != null) {
            group.setName(name);
        }
        if (color != null) {
            group.setColor(color);
        }
        if (layout != null) {
            if (!List.of("free", "grid", "horizontal").contains(layout)) {
                throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "布局类型必须是 free/grid/horizontal");
            }
            group.setLayout(layout);
        }
        if (nodeIds != null) {
            group.setNodeIds(nodeIds);
        }
        group.setUpdatedAt(OffsetDateTime.now());
        groupMapper.updateById(group);
        return canvasService.toGroupPayload(group);
    }

    @Transactional
    public void deleteGroup(Long canvasId, Long groupId) {
        canvasService.requireOwned(canvasId);
        CanvasGroup group = requireGroup(canvasId, groupId);
        group.getNodeIds().forEach(id -> {
            CanvasNode n = nodeMapper.selectById(id);
            if (n != null) {
                n.setGroupId(null);
                nodeMapper.updateById(n);
            }
        });
        groupMapper.deleteById(groupId);
    }

    @Transactional
    public CanvasDtos.StackPayload addStack(Long canvasId, List<Long> nodeIds) {
        canvasService.requireOwned(canvasId);
        if (nodeIds == null || nodeIds.size() < 2) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "堆叠至少需要 2 个节点");
        }
        CanvasStack stack = new CanvasStack();
        stack.setId(idGenerator.nextId());
        stack.setCanvasId(canvasId);
        stack.setCollapsed(true);
        stack.setNodeIds(nodeIds);
        stack.setDeleted(false);
        stack.setCreatedAt(OffsetDateTime.now());
        stack.setUpdatedAt(OffsetDateTime.now());
        stackMapper.insert(stack);
        nodeIds.forEach(id -> {
            CanvasNode n = requireNode(canvasId, id);
            n.setStackId(stack.getId());
            nodeMapper.updateById(n);
        });
        return canvasService.toStackPayload(stack);
    }

    @Transactional
    public CanvasDtos.StackPayload updateStack(Long canvasId, Long stackId, Boolean collapsed) {
        canvasService.requireOwned(canvasId);
        CanvasStack stack = requireStack(canvasId, stackId);
        if (collapsed != null) {
            stack.setCollapsed(collapsed);
        }
        stack.setUpdatedAt(OffsetDateTime.now());
        stackMapper.updateById(stack);
        return canvasService.toStackPayload(stack);
    }

    @Transactional
    public CanvasDtos.NodePayload extractFromStack(Long canvasId, Long stackId, Long nodeId) {
        canvasService.requireOwned(canvasId);
        CanvasStack stack = requireStack(canvasId, stackId);
        CanvasNode node = requireNode(canvasId, nodeId);
        if (!stack.getNodeIds().contains(nodeId)) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "该节点不在堆叠中");
        }
        List<Long> remaining = stack.getNodeIds().stream().filter(id -> !id.equals(nodeId)).toList();
        stack.setNodeIds(remaining);
        stack.setUpdatedAt(OffsetDateTime.now());
        stackMapper.updateById(stack);
        if (remaining.isEmpty()) {
            stackMapper.deleteById(stackId);
        }
        node.setStackId(null);
        nodeMapper.updateById(node);
        return canvasService.toNodePayload(node);
    }

    @Transactional
    public void deleteStack(Long canvasId, Long stackId) {
        canvasService.requireOwned(canvasId);
        CanvasStack stack = requireStack(canvasId, stackId);
        stack.getNodeIds().forEach(id -> {
            CanvasNode n = nodeMapper.selectById(id);
            if (n != null) {
                n.setStackId(null);
                nodeMapper.updateById(n);
            }
        });
        stackMapper.deleteById(stackId);
    }

    private CanvasNode requireNode(Long canvasId, Long nodeId) {
        CanvasNode node = nodeMapper.selectById(nodeId);
        if (node == null || !node.getCanvasId().equals(canvasId)) {
            throw ApiException.notFound("节点不存在");
        }
        return node;
    }

    private CanvasGroup requireGroup(Long canvasId, Long groupId) {
        CanvasGroup group = groupMapper.selectById(groupId);
        if (group == null || !group.getCanvasId().equals(canvasId)) {
            throw ApiException.notFound("编组不存在");
        }
        return group;
    }

    private CanvasStack requireStack(Long canvasId, Long stackId) {
        CanvasStack stack = stackMapper.selectById(stackId);
        if (stack == null || !stack.getCanvasId().equals(canvasId)) {
            throw ApiException.notFound("堆叠不存在");
        }
        return stack;
    }

    private String nodeName(CanvasNode n) {
        return switch (n.getNodeType()) {
            case "text" -> "文本节点";
            case "image" -> "图片节点";
            case "video" -> "视频节点";
            case "audio" -> "音频节点";
            case "compose" -> "合成节点";
            case "director" -> "导演台节点";
            default -> "节点";
        };
    }

    private <T> T replay(String idempotencyKey, Long canvasId, String operation, Class<T> type) {
        CanvasGraphCommand command = claim(canvasId, idempotencyKey, operation);
        if (command.getResultSnapshot() == null || "{}".equals(command.getResultSnapshot())) return null;
        try {
            return objectMapper.readValue(command.getResultSnapshot(), type);
        } catch (Exception e) {
            throw new IllegalStateException("画布命令结果快照损坏", e);
        }
    }

    private Map<String, Object> replayMap(String idempotencyKey, Long canvasId, String operation) {
        CanvasGraphCommand command = claim(canvasId, idempotencyKey, operation);
        if (command.getResultSnapshot() == null || "{}".equals(command.getResultSnapshot())) return null;
        try {
            return objectMapper.readValue(command.getResultSnapshot(), new TypeReference<>() {
            });
        } catch (Exception e) {
            throw new IllegalStateException("画布命令结果快照损坏", e);
        }
    }

    private CanvasGraphCommand claim(Long canvasId, String idempotencyKey, String operation) {
        if (idempotencyKey == null || idempotencyKey.isBlank() || idempotencyKey.length() > 128) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "Idempotency-Key 必须为 1-128 个字符");
        }
        Map<String, Object> params = Map.of(
                "id", idGenerator.nextId(),
                "canvasId", canvasId,
                "idempotencyKey", idempotencyKey,
                "operation", operation);
        return graphCommandMapper.claim(params);
    }

    private void remember(Long canvasId, String idempotencyKey, String operation, Object result) {
        try {
            CanvasGraphCommand command = graphCommandMapper.selectOne(new LambdaQueryWrapper<CanvasGraphCommand>()
                    .eq(CanvasGraphCommand::getCanvasId, canvasId)
                    .eq(CanvasGraphCommand::getIdempotencyKey, idempotencyKey));
            command.setOperation(operation);
            command.setResultCanvasVersion(canvasService.getById(canvasId).getVersion());
            command.setResultSnapshot(objectMapper.writeValueAsString(result));
            graphCommandMapper.updateById(command);
        } catch (Exception e) {
            throw new IllegalStateException("画布命令结果快照写入失败", e);
        }
    }

    private String writeJson(Object obj) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private String extractPrompt(Map<String, Object> params) {
        if (params == null) {
            return null;
        }
        Object p = params.get("prompt");
        if (p == null) {
            p = params.get("title");
        }
        return p == null ? null : p.toString();
    }

    /** Norm 一等字段与 params JSON 双向同步（过渡期）。 */
    private void syncParamsFromNorm(CanvasNode node) {
        try {
            Map<String, Object> params = node.getParams() == null ? new HashMap<>()
                    : new com.fasterxml.jackson.databind.ObjectMapper().readValue(node.getParams(), new com.fasterxml.jackson.core.type.TypeReference<>() {
            });
            if (node.getModelRef() != null) {
                params.put("model", node.getModelRef());
            }
            if (node.getPrompt() != null) {
                params.put("prompt", node.getPrompt());
            }
            if (node.getOutput() != null && !node.getOutput().isBlank()) {
                Object out = new com.fasterxml.jackson.databind.ObjectMapper().readValue(node.getOutput(), Object.class);
                if (out instanceof Map<?, ?> m && m.get("url") != null) {
                    Object url = m.get("url");
                    params.put("output_url", url);
                    params.putIfAbsent("lastOutputUrl", url);
                    params.putIfAbsent("url", url);
                } else {
                    params.put("output", out);
                }
            }
            node.setParams(writeJson(params));
        } catch (Exception ignored) {
        }
    }
}
