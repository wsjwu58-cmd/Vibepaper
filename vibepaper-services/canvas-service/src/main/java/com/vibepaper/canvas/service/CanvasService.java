package com.vibepaper.canvas.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.vibepaper.canvas.domain.EdgeRules;
import com.vibepaper.canvas.dto.CanvasDtos;
import com.vibepaper.canvas.entity.*;
import com.vibepaper.canvas.mapper.*;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.api.PageResult;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class CanvasService {
    public static final String CURRENT_SCHEMA_VERSION = "1.0.0";

    private final CanvasMapper canvasMapper;
    private final CanvasNodeMapper nodeMapper;
    private final CanvasEdgeMapper edgeMapper;
    private final CanvasGroupMapper groupMapper;
    private final CanvasStackMapper stackMapper;
    private final CanvasRevisionMapper revisionMapper;
    private final CanvasShareMapper shareMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final ObjectMapper objectMapper;

    @Transactional
    public CanvasDtos.CanvasView create(CanvasDtos.CreateCanvasRequest req) {
        return createForInternal(req, RequestContext.userIdLong());
    }

    @Transactional
    public CanvasDtos.CanvasView createForInternal(CanvasDtos.CreateCanvasRequest req, Long ownerId) {
        Canvas canvas = new Canvas();
        canvas.setId(idGenerator.nextId());
        canvas.setOwnerId(ownerId);
        canvas.setName(req.name());
        canvas.setDescription(req.description());
        canvas.setSchemaVersion(CURRENT_SCHEMA_VERSION);
        canvas.setVersion(1);
        canvas.setVisibility("private");
        canvas.setShareToken(UUID.randomUUID().toString().replace("-", ""));
        canvas.setDeleted(false);
        canvas.setCreatedAt(OffsetDateTime.now());
        canvas.setUpdatedAt(OffsetDateTime.now());
        canvasMapper.insert(canvas);
        return toView(canvas);
    }

    public PageResult<CanvasDtos.CanvasView> list(int page, int pageSize, String keyword) {
        Long userId = RequestContext.userIdLong();
        Page<Canvas> p = canvasMapper.selectPage(new Page<>(page, pageSize),
                new LambdaQueryWrapper<Canvas>()
                        .eq(Canvas::getOwnerId, userId)
                        .like(keyword != null && !keyword.isBlank(), Canvas::getName, keyword)
                        .orderByDesc(Canvas::getUpdatedAt));
        return PageResult.of(p.getRecords().stream().map(this::toView).toList(), p.getTotal(), page, pageSize);
    }

    public CanvasDtos.CanvasDetail detail(Long canvasId) {
        Canvas canvas = requireOwned(canvasId);
        return buildDetail(canvas);
    }

    public CanvasDtos.CanvasView update(Long canvasId, CanvasDtos.UpdateCanvasRequest req) {
        Canvas canvas = requireOwned(canvasId);
        if (req.name() != null && !req.name().isBlank()) {
            canvas.setName(req.name());
        }
        if (req.description() != null) {
            canvas.setDescription(req.description());
        }
        if (req.thumbnailUrl() != null) {
            canvas.setThumbnailUrl(req.thumbnailUrl());
        }
        canvas.setUpdatedAt(OffsetDateTime.now());
        canvasMapper.updateById(canvas);
        return toView(canvas);
    }

    @Transactional
    public void delete(Long canvasId) {
        Canvas canvas = requireOwned(canvasId);
        canvasMapper.deleteById(canvasId);
        nodeMapper.delete(new LambdaQueryWrapper<CanvasNode>().eq(CanvasNode::getCanvasId, canvasId));
        edgeMapper.delete(new LambdaQueryWrapper<CanvasEdge>().eq(CanvasEdge::getCanvasId, canvasId));
        groupMapper.delete(new LambdaQueryWrapper<CanvasGroup>().eq(CanvasGroup::getCanvasId, canvasId));
        stackMapper.delete(new LambdaQueryWrapper<CanvasStack>().eq(CanvasStack::getCanvasId, canvasId));
    }

    @Transactional
    public CanvasDtos.CanvasDetail save(Long canvasId, CanvasDtos.SaveCanvasRequest req) {
        Canvas canvas = requireOwned(canvasId);
        if (!canvas.getVersion().equals(req.version())) {
            throw ApiException.conflict(ErrorCode.VERSION_CONFLICT, "画布已在其他会话更新，请刷新");
        }

        // 全量替换节点/连线/编组/堆叠
        nodeMapper.delete(new LambdaQueryWrapper<CanvasNode>().eq(CanvasNode::getCanvasId, canvasId));
        edgeMapper.delete(new LambdaQueryWrapper<CanvasEdge>().eq(CanvasEdge::getCanvasId, canvasId));
        groupMapper.delete(new LambdaQueryWrapper<CanvasGroup>().eq(CanvasGroup::getCanvasId, canvasId));
        stackMapper.delete(new LambdaQueryWrapper<CanvasStack>().eq(CanvasStack::getCanvasId, canvasId));

        Set<Long> nodeIds = new HashSet<>();
        if (req.nodes() != null) {
            for (CanvasDtos.NodePayload n : req.nodes()) {
                if (!EdgeRules.isValidNodeType(n.type())) {
                    throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "非法节点类型: " + n.type());
                }
                CanvasNode node = new CanvasNode();
                node.setId(n.id());
                node.setCanvasId(canvasId);
                node.setNodeType(n.type());
                node.setPositionX(n.x());
                node.setPositionY(n.y());
                node.setWidth(n.width());
                node.setHeight(n.height());
                node.setParams(n.params() == null ? "{}" : writeJson(n.params()));
                node.setStatus(n.status() == null ? "idle" : n.status());
                node.setCreativeType(n.creativeType());
                node.setStale(Boolean.TRUE.equals(n.stale()));
                node.setModelRef(n.modelRef());
                node.setPrompt(n.prompt());
                node.setExecStatus(n.execStatus() == null ? "idle" : n.execStatus());
                if (n.output() != null) {
                    node.setOutput(writeJson(n.output()));
                }
                node.setCurrentOutputId(n.currentOutputId());
                node.setGroupId(n.groupId());
                node.setStackId(n.stackId());
                node.setDeleted(false);
                node.setCreatedAt(OffsetDateTime.now());
                node.setUpdatedAt(OffsetDateTime.now());
                nodeMapper.insert(node);
                nodeIds.add(n.id());
            }
        }

        Set<Long> validNodeIds = nodeIds;
        if (req.edges() != null) {
            for (CanvasDtos.EdgePayload e : req.edges()) {
                if (!validNodeIds.contains(e.sourceNodeId()) || !validNodeIds.contains(e.targetNodeId())) {
                    continue;
                }
                CanvasNode source = nodeMapper.selectById(e.sourceNodeId());
                CanvasNode target = nodeMapper.selectById(e.targetNodeId());
                boolean compatible = source != null && target != null
                        && EdgeRules.isCompatible(source.getNodeType(), target.getNodeType());
                CanvasEdge edge = new CanvasEdge();
                edge.setId(e.id());
                edge.setCanvasId(canvasId);
                edge.setSourceNodeId(e.sourceNodeId());
                edge.setSourcePort(e.sourcePort() == null ? "output" : e.sourcePort());
                edge.setTargetNodeId(e.targetNodeId());
                edge.setTargetPort(e.targetPort() == null ? "input" : e.targetPort());
                edge.setValid(e.valid() == null ? compatible : e.valid() && compatible);
                edge.setDependencyType(e.dependencyType() == null ? "reference" : e.dependencyType());
                edge.setDeleted(false);
                edge.setCreatedAt(OffsetDateTime.now());
                edge.setUpdatedAt(OffsetDateTime.now());
                edgeMapper.insert(edge);
            }
        }
        if (req.groups() != null) {
            for (CanvasDtos.GroupPayload g : req.groups()) {
                CanvasGroup group = new CanvasGroup();
                group.setId(g.id());
                group.setCanvasId(canvasId);
                group.setName(g.name() == null ? "编组" : g.name());
                group.setColor(g.color() == null ? "#8b5cf6" : g.color());
                group.setLayout(g.layout() == null ? "free" : g.layout());
                group.setNodeIds(g.nodeIds() == null ? List.of() : g.nodeIds());
                group.setDeleted(false);
                group.setCreatedAt(OffsetDateTime.now());
                group.setUpdatedAt(OffsetDateTime.now());
                groupMapper.insert(group);
            }
        }
        if (req.stacks() != null) {
            for (CanvasDtos.StackPayload s : req.stacks()) {
                CanvasStack stack = new CanvasStack();
                stack.setId(s.id());
                stack.setCanvasId(canvasId);
                stack.setCollapsed(s.collapsed() == null || s.collapsed());
                stack.setNodeIds(s.nodeIds() == null ? List.of() : s.nodeIds());
                stack.setDeleted(false);
                stack.setCreatedAt(OffsetDateTime.now());
                stack.setUpdatedAt(OffsetDateTime.now());
                stackMapper.insert(stack);
            }
        }

        // 乐观锁：version +1
        canvas.setVersion(canvas.getVersion() + 1);
        canvas.setUpdatedAt(OffsetDateTime.now());
        int updated = canvasMapper.updateById(canvas);
        if (updated == 0) {
            throw ApiException.conflict(ErrorCode.VERSION_CONFLICT, "画布已在其他会话更新，请刷新");
        }

        CanvasRevision revision = new CanvasRevision();
        revision.setId(idGenerator.nextId());
        revision.setCanvasId(canvasId);
        revision.setVersion(canvas.getVersion());
        revision.setPayload(writeJson(buildDetail(canvas).nodes()));
        revision.setCreatedAt(OffsetDateTime.now());
        revisionMapper.insert(revision);

        return buildDetail(canvas);
    }

    public Map<String, Object> export(Long canvasId) {
        Canvas canvas = requireOwned(canvasId);
        return buildExportDoc(canvas);
    }

    public Map<String, Object> exportInternalForOwner(Long canvasId) {
        Canvas canvas = canvasMapper.selectById(canvasId);
        if (canvas == null) {
            throw ApiException.notFound("画布不存在");
        }
        return buildExportDoc(canvas);
    }

    private Map<String, Object> buildExportDoc(Canvas canvas) {
        CanvasDtos.CanvasDetail detail = buildDetail(canvas);
        Map<String, Object> doc = new HashMap<>();
        doc.put("schema_version", CURRENT_SCHEMA_VERSION);
        doc.put("schemaVersion", CURRENT_SCHEMA_VERSION);
        doc.put("canvas", detail.canvas());
        doc.put("nodes", detail.nodes());
        doc.put("edges", detail.edges());
        doc.put("groups", detail.groups());
        doc.put("stacks", detail.stacks());
        return doc;
    }

    @Transactional
    public CanvasDtos.CanvasDetail importCanvas(String json, Long ownerId) {
        Map<String, Object> doc;
        try {
            doc = objectMapper.readValue(json, new TypeReference<>() {
            });
        } catch (Exception e) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "画布 JSON 格式错误: " + e.getMessage());
        }
        Object schemaVer = doc.get("schema_version");
        if (schemaVer == null) {
            schemaVer = doc.get("schemaVersion");
        }
        if (schemaVer == null) {
            throw ApiException.badRequest(ErrorCode.SCHEMA_INCOMPATIBLE, "缺少 schema_version，导入拒绝");
        }
        String version = schemaVer.toString();
        if (!isSchemaCompatible(version)) {
            throw ApiException.badRequest(ErrorCode.SCHEMA_INCOMPATIBLE,
                    "画布版本不兼容：导入版本 " + version + "，当前最低兼容 " + CURRENT_SCHEMA_VERSION);
        }

        Canvas canvas = new Canvas();
        canvas.setId(idGenerator.nextId());
        canvas.setOwnerId(ownerId == null ? RequestContext.userIdLong() : ownerId);
        Map<String, Object> canvasInfo = (Map<String, Object>) doc.getOrDefault("canvas", Map.of());
        canvas.setName(canvasInfo.get("name") == null ? "导入的画布" : canvasInfo.get("name").toString());
        canvas.setDescription(canvasInfo.get("description") == null ? null : canvasInfo.get("description").toString());
        canvas.setSchemaVersion(CURRENT_SCHEMA_VERSION);
        canvas.setVersion(1);
        canvas.setVisibility("private");
        canvas.setShareToken(UUID.randomUUID().toString().replace("-", ""));
        canvas.setDeleted(false);
        canvas.setCreatedAt(OffsetDateTime.now());
        canvas.setUpdatedAt(OffsetDateTime.now());
        canvasMapper.insert(canvas);

        Map<String, Long> idMap = new HashMap<>();
        List<Map<String, Object>> nodes = (List<Map<String, Object>>) doc.getOrDefault("nodes", List.of());
        for (Map<String, Object> n : nodes) {
            Long oldId = ((Number) n.get("id")).longValue();
            Long newId = idGenerator.nextId();
            idMap.put(oldId.toString(), newId);
            CanvasNode node = new CanvasNode();
            node.setId(newId);
            node.setCanvasId(canvas.getId());
            node.setNodeType(n.get("type").toString());
            node.setPositionX(n.get("x") == null ? 100 : ((Number) n.get("x")).doubleValue());
            node.setPositionY(n.get("y") == null ? 100 : ((Number) n.get("y")).doubleValue());
            node.setWidth(n.get("width") == null ? 260 : ((Number) n.get("width")).doubleValue());
            node.setHeight(n.get("height") == null ? 200 : ((Number) n.get("height")).doubleValue());
            node.setParams(n.get("params") == null ? "{}" : writeJson(n.get("params")));
            node.setStatus("idle");
            Object ct = n.get("creativeType");
            if (ct == null) {
                ct = n.get("creative_type");
            }
            node.setCreativeType(ct == null ? null : ct.toString());
            node.setStale(false);
            node.setDeleted(false);
            node.setCreatedAt(OffsetDateTime.now());
            node.setUpdatedAt(OffsetDateTime.now());
            nodeMapper.insert(node);
        }

        List<Map<String, Object>> edges = (List<Map<String, Object>>) doc.getOrDefault("edges", List.of());
        for (Map<String, Object> e : edges) {
            Long newSource = idMap.get(String.valueOf(((Number) e.get("sourceNodeId")).longValue()));
            Long newTarget = idMap.get(String.valueOf(((Number) e.get("targetNodeId")).longValue()));
            if (newSource == null || newTarget == null) {
                continue;
            }
            CanvasNode source = nodeMapper.selectById(newSource);
            CanvasNode target = nodeMapper.selectById(newTarget);
            CanvasEdge edge = new CanvasEdge();
            edge.setId(idGenerator.nextId());
            edge.setCanvasId(canvas.getId());
            edge.setSourceNodeId(newSource);
            edge.setSourcePort(e.get("sourcePort") == null ? "output" : e.get("sourcePort").toString());
            edge.setTargetNodeId(newTarget);
            edge.setTargetPort(e.get("targetPort") == null ? "input" : e.get("targetPort").toString());
            edge.setValid(source != null && target != null
                    && EdgeRules.isCompatible(source.getNodeType(), target.getNodeType()));
            Object dep = e.get("dependencyType");
            if (dep == null) {
                dep = e.get("dependency_type");
            }
            edge.setDependencyType(dep == null ? "reference" : dep.toString());
            edge.setDeleted(false);
            edge.setCreatedAt(OffsetDateTime.now());
            edge.setUpdatedAt(OffsetDateTime.now());
            edgeMapper.insert(edge);
        }
        return buildDetail(canvas);
    }

    @Transactional
    public CanvasDtos.CanvasDetail share(Long canvasId, CanvasDtos.ShareRequest req) {
        Canvas canvas = requireOwned(canvasId);
        String visibility = req.visibility();
        if (!Set.of("private", "link", "public").contains(visibility)) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "共享状态必须是 private/link/public");
        }
        canvas.setVisibility(visibility);
        canvas.setUpdatedAt(OffsetDateTime.now());
        canvasMapper.updateById(canvas);
        CanvasShare share = shareMapper.selectOne(new LambdaQueryWrapper<CanvasShare>().eq(CanvasShare::getCanvasId, canvasId));
        if (share == null) {
            share = new CanvasShare();
            share.setId(idGenerator.nextId());
            share.setCanvasId(canvasId);
            share.setToken(UUID.randomUUID().toString().replace("-", ""));
            share.setVisibility(visibility);
            share.setCreatedAt(OffsetDateTime.now());
            share.setUpdatedAt(OffsetDateTime.now());
            shareMapper.insert(share);
        } else {
            share.setVisibility(visibility);
            share.setUpdatedAt(OffsetDateTime.now());
            shareMapper.updateById(share);
        }
        return buildDetail(canvas);
    }

    public CanvasDtos.CanvasDetail viewShared(String token) {
        CanvasShare share = shareMapper.selectOne(new LambdaQueryWrapper<CanvasShare>().eq(CanvasShare::getToken, token));
        if (share == null) {
            throw ApiException.notFound("分享链接不存在");
        }
        Canvas canvas = canvasMapper.selectById(share.getCanvasId());
        if (canvas == null || "private".equals(share.getVisibility())) {
            throw ApiException.forbidden("该画布未公开");
        }
        return buildDetail(canvas);
    }

    public Canvas requireOwned(Long canvasId) {
        Canvas canvas = canvasMapper.selectById(canvasId);
        Long userId = RequestContext.userIdLong();
        if (canvas == null) {
            throw ApiException.notFound("画布不存在");
        }
        if (userId == null || !canvas.getOwnerId().equals(userId)) {
            throw ApiException.forbidden("无权访问该画布");
        }
        return canvas;
    }

    public Canvas getById(Long canvasId) {
        return canvasMapper.selectById(canvasId);
    }

    public CanvasDtos.CanvasDetail buildDetail(Canvas canvas) {
        List<CanvasNode> nodes = nodeMapper.selectList(new LambdaQueryWrapper<CanvasNode>()
                .eq(CanvasNode::getCanvasId, canvas.getId()));
        List<CanvasEdge> edges = edgeMapper.selectList(new LambdaQueryWrapper<CanvasEdge>()
                .eq(CanvasEdge::getCanvasId, canvas.getId()));
        List<CanvasGroup> groups = groupMapper.selectList(new LambdaQueryWrapper<CanvasGroup>()
                .eq(CanvasGroup::getCanvasId, canvas.getId()));
        List<CanvasStack> stacks = stackMapper.selectList(new LambdaQueryWrapper<CanvasStack>()
                .eq(CanvasStack::getCanvasId, canvas.getId()));
        return new CanvasDtos.CanvasDetail(toView(canvas),
                nodes.stream().map(this::toNodePayload).toList(),
                edges.stream().map(this::toEdgePayload).toList(),
                groups.stream().map(this::toGroupPayload).toList(),
                stacks.stream().map(this::toStackPayload).toList());
    }

    public CanvasDtos.NodePayload toNodePayload(CanvasNode n) {
        Map<String, Object> params;
        Map<String, Object> outputMap = null;
        try {
            params = n.getParams() == null ? new HashMap<>() : objectMapper.readValue(n.getParams(), new TypeReference<>() {
            });
        } catch (Exception e) {
            params = new HashMap<>();
        }
        try {
            if (n.getOutput() != null && !n.getOutput().isBlank()) {
                outputMap = objectMapper.readValue(n.getOutput(), new TypeReference<>() {
                });
            }
        } catch (Exception ignored) {
        }
        return new CanvasDtos.NodePayload(n.getId(), n.getNodeType(), n.getPositionX(), n.getPositionY(),
                n.getWidth(), n.getHeight(), params, n.getStatus(), n.getCurrentOutputId(),
                n.getGroupId(), n.getStackId(), n.getCreativeType(),
                Boolean.TRUE.equals(n.getStale()), n.getModelRef(), n.getPrompt(), outputMap,
                n.getExecStatus() == null ? "idle" : n.getExecStatus());
    }

    public CanvasDtos.EdgePayload toEdgePayload(CanvasEdge e) {
        return new CanvasDtos.EdgePayload(e.getId(), e.getSourceNodeId(), e.getSourcePort(),
                e.getTargetNodeId(), e.getTargetPort(), e.getValid(),
                e.getDependencyType() == null ? "reference" : e.getDependencyType());
    }

    /**
     * Agent 上下文摘要：节点统计 / 关键词 / 连线有效性 / 选中与上下游 / stale。
     */
    public Map<String, Object> buildSummary(Long canvasId, List<Long> selectedNodeIds, int relatedDepth) {
        Canvas canvas = canvasMapper.selectById(canvasId);
        if (canvas == null) {
            throw ApiException.notFound("画布不存在");
        }
        List<CanvasNode> nodes = nodeMapper.selectList(new LambdaQueryWrapper<CanvasNode>()
                .eq(CanvasNode::getCanvasId, canvasId));
        List<CanvasEdge> edges = edgeMapper.selectList(new LambdaQueryWrapper<CanvasEdge>()
                .eq(CanvasEdge::getCanvasId, canvasId));

        Map<String, Long> typeCounts = nodes.stream()
                .collect(Collectors.groupingBy(CanvasNode::getNodeType, Collectors.counting()));
        Map<String, Long> creativeCounts = nodes.stream()
                .filter(n -> n.getCreativeType() != null && !n.getCreativeType().isBlank())
                .collect(Collectors.groupingBy(CanvasNode::getCreativeType, Collectors.counting()));

        List<String> keywords = new ArrayList<>();
        for (CanvasNode n : nodes) {
            try {
                Map<String, Object> p = n.getParams() == null ? Map.of()
                        : objectMapper.readValue(n.getParams(), new TypeReference<>() {
                });
                Object prompt = p.get("prompt");
                if (prompt != null) {
                    String text = prompt.toString().trim();
                    if (!text.isEmpty()) {
                        keywords.add(text.length() > 24 ? text.substring(0, 24) : text);
                    }
                }
            } catch (Exception ignored) {
            }
            if (keywords.size() >= 8) {
                break;
            }
        }

        long validEdges = edges.stream().filter(e -> Boolean.TRUE.equals(e.getValid())).count();
        List<Map<String, Object>> staleNodes = nodes.stream()
                .filter(n -> Boolean.TRUE.equals(n.getStale()))
                .map(n -> {
                    Map<String, Object> m = new HashMap<>();
                    m.put("nodeId", n.getId());
                    m.put("type", n.getNodeType());
                    m.put("creativeType", n.getCreativeType());
                    m.put("reason", "上游 input 依赖已变更");
                    return m;
                }).toList();

        Set<Long> selected = selectedNodeIds == null ? Set.of() : new HashSet<>(selectedNodeIds);
        Set<Long> relatedIds = new HashSet<>(selected);
        if (relatedDepth > 0 && !selected.isEmpty()) {
            Map<Long, List<CanvasEdge>> out = edges.stream().collect(Collectors.groupingBy(CanvasEdge::getSourceNodeId));
            Map<Long, List<CanvasEdge>> in = edges.stream().collect(Collectors.groupingBy(CanvasEdge::getTargetNodeId));
            Set<Long> frontier = new HashSet<>(selected);
            for (int d = 0; d < relatedDepth; d++) {
                Set<Long> next = new HashSet<>();
                for (Long id : frontier) {
                    for (CanvasEdge e : out.getOrDefault(id, List.of())) {
                        next.add(e.getTargetNodeId());
                    }
                    for (CanvasEdge e : in.getOrDefault(id, List.of())) {
                        next.add(e.getSourceNodeId());
                    }
                }
                relatedIds.addAll(next);
                frontier = next;
            }
        }

        List<Map<String, Object>> nodeBriefs = nodes.stream().map(n -> {
            Map<String, Object> m = new HashMap<>();
            m.put("id", n.getId());
            m.put("type", n.getNodeType());
            m.put("status", n.getStatus());
            m.put("creativeType", n.getCreativeType());
            m.put("stale", Boolean.TRUE.equals(n.getStale()));
            m.put("modelRef", n.getModelRef());
            m.put("execStatus", n.getExecStatus() == null ? "idle" : n.getExecStatus());
            if (n.getPrompt() != null) {
                String p = n.getPrompt().trim();
                m.put("prompt", p.length() > 48 ? p.substring(0, 48) : p);
            }
            return m;
        }).toList();

        List<Map<String, Object>> selectedBriefs = nodeBriefs.stream()
                .filter(m -> selected.contains(((Number) m.get("id")).longValue()))
                .toList();
        List<Map<String, Object>> relatedBriefs = nodeBriefs.stream()
                .filter(m -> relatedIds.contains(((Number) m.get("id")).longValue()))
                .toList();

        String pipelineHint = "text_base";
        if (creativeCounts.containsKey("composite") || typeCounts.containsKey("compose")) {
            pipelineHint = "post_production";
        } else if (creativeCounts.containsKey("clip") || typeCounts.containsKey("video")) {
            pipelineHint = "dynamic_gen";
        } else if (creativeCounts.containsKey("keyframe") || typeCounts.containsKey("image")) {
            pipelineHint = "visual_anchor";
        } else if (creativeCounts.containsKey("shot")) {
            pipelineHint = "storyboard";
        }

        Map<String, Object> summary = new HashMap<>();
        summary.put("canvasId", canvasId);
        summary.put("name", canvas.getName());
        summary.put("version", canvas.getVersion());
        summary.put("nodeCount", nodes.size());
        summary.put("edgeCount", edges.size());
        summary.put("nodeTypeCounts", typeCounts);
        summary.put("creativeTypeCounts", creativeCounts);
        summary.put("keywords", keywords);
        summary.put("validEdgeCount", validEdges);
        summary.put("invalidEdgeCount", edges.size() - validEdges);
        summary.put("staleNodes", staleNodes);
        summary.put("selectedNodes", selectedBriefs);
        summary.put("relatedNodes", relatedBriefs);
        summary.put("nodes", nodeBriefs);
        summary.put("edges", edges.stream().map(e -> {
            Map<String, Object> m = new HashMap<>();
            m.put("id", e.getId());
            m.put("source", e.getSourceNodeId());
            m.put("target", e.getTargetNodeId());
            m.put("valid", e.getValid());
            m.put("dependencyType", e.getDependencyType() == null ? "reference" : e.getDependencyType());
            return m;
        }).toList());
        summary.put("pipelineHint", pipelineHint);
        if (!selected.isEmpty()) {
            summary.put("inputChains", buildInputChains(nodes, edges, selected));
        }
        return summary;
    }

    /** 选中节点的 input 依赖上游链（Agent 拓扑规划）。 */
    private Map<String, List<Map<String, Object>>> buildInputChains(List<CanvasNode> nodes,
                                                                     List<CanvasEdge> edges,
                                                                     Set<Long> selected) {
        Map<Long, CanvasNode> byId = nodes.stream().collect(Collectors.toMap(CanvasNode::getId, n -> n));
        Map<Long, List<Long>> inputByTarget = edges.stream()
                .filter(e -> "input".equals(e.getDependencyType()))
                .collect(Collectors.groupingBy(CanvasEdge::getTargetNodeId,
                        Collectors.mapping(CanvasEdge::getSourceNodeId, Collectors.toList())));
        Map<String, List<Map<String, Object>>> chains = new HashMap<>();
        for (Long targetId : selected) {
            List<Map<String, Object>> chain = new ArrayList<>();
            Set<Long> seen = new HashSet<>();
            collectInputUpstream(targetId, inputByTarget, byId, chain, seen);
            chains.put(String.valueOf(targetId), chain);
        }
        return chains;
    }

    private void collectInputUpstream(Long nodeId, Map<Long, List<Long>> inputByTarget,
                                      Map<Long, CanvasNode> byId, List<Map<String, Object>> chain, Set<Long> seen) {
        for (Long src : inputByTarget.getOrDefault(nodeId, List.of())) {
            if (!seen.add(src)) {
                continue;
            }
            collectInputUpstream(src, inputByTarget, byId, chain, seen);
            CanvasNode n = byId.get(src);
            if (n != null) {
                Map<String, Object> m = new HashMap<>();
                m.put("id", n.getId());
                m.put("type", n.getNodeType());
                m.put("creativeType", n.getCreativeType());
                m.put("execStatus", n.getExecStatus());
                chain.add(m);
            }
        }
    }

    /** 上游节点变更时，沿 input 连线将下游标 stale。 */
    public void markDownstreamStale(Long canvasId, Long sourceNodeId) {
        List<CanvasEdge> outs = edgeMapper.selectList(new LambdaQueryWrapper<CanvasEdge>()
                .eq(CanvasEdge::getCanvasId, canvasId)
                .eq(CanvasEdge::getSourceNodeId, sourceNodeId)
                .eq(CanvasEdge::getDependencyType, "input"));
        for (CanvasEdge e : outs) {
            CanvasNode target = nodeMapper.selectById(e.getTargetNodeId());
            if (target != null && !Boolean.TRUE.equals(target.getStale())) {
                target.setStale(true);
                target.setExecStatus("stale");
                if (!"queued".equals(target.getStatus()) && !"running".equals(target.getStatus())) {
                    // 保留任务态；其余标记 stale 语义
                }
                target.setUpdatedAt(OffsetDateTime.now());
                nodeMapper.updateById(target);
                markDownstreamStale(canvasId, target.getId());
            }
        }
    }

    public CanvasDtos.GroupPayload toGroupPayload(CanvasGroup g) {
        return new CanvasDtos.GroupPayload(g.getId(), g.getName(), g.getColor(), g.getLayout(), g.getNodeIds());
    }

    public CanvasDtos.StackPayload toStackPayload(CanvasStack s) {
        return new CanvasDtos.StackPayload(s.getId(), s.getCollapsed(), s.getNodeIds());
    }

    public CanvasDtos.CanvasView toView(Canvas c) {
        return new CanvasDtos.CanvasView(c.getId(), c.getOwnerId(), c.getName(), c.getDescription(),
                c.getSchemaVersion(), c.getVersion(), c.getThumbnailUrl(), c.getVisibility(), c.getShareToken(),
                c.getCreatedAt() == null ? null : c.getCreatedAt().toString(),
                c.getUpdatedAt() == null ? null : c.getUpdatedAt().toString());
    }

    private boolean isSchemaCompatible(String version) {
        try {
            String[] parts = version.split("\\.");
            int major = Integer.parseInt(parts[0]);
            return major >= 1;
        } catch (Exception e) {
            return false;
        }
    }

    private String writeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
