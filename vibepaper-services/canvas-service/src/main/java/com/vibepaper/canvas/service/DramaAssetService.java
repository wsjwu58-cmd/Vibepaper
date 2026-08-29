package com.vibepaper.canvas.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.vibepaper.canvas.dto.CanvasDtos;
import com.vibepaper.canvas.entity.Canvas;
import com.vibepaper.canvas.entity.DramaAsset;
import com.vibepaper.canvas.entity.DramaAssetCommand;
import com.vibepaper.canvas.mapper.CanvasMapper;
import com.vibepaper.canvas.mapper.DramaAssetCommandMapper;
import com.vibepaper.canvas.mapper.DramaAssetMapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 结构化短剧资产的真相源；不把整份资产塞进画布节点 JSON。 */
@Service
@RequiredArgsConstructor
public class DramaAssetService {
    private static final Set<String> ASSET_TYPES = Set.of(
            "series_bible", "episode", "scene", "character_profile", "character_look",
            "shot_spec", "continuity_constraint", "audio_cue", "subtitle_cue");

    private final CanvasService canvasService;
    private final CanvasMapper canvasMapper;
    private final DramaAssetMapper dramaAssetMapper;
    private final DramaAssetCommandMapper dramaAssetCommandMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final ObjectMapper objectMapper;

    @Transactional
    public CanvasDtos.DramaAssetPayload upsert(Long canvasId, String idempotencyKey,
                                                CanvasDtos.UpsertDramaAssetRequest req) {
        Canvas canvas = canvasService.requireOwned(canvasId);
        String key = requireIdempotencyKey(idempotencyKey);
        DramaAssetCommand previous = findCommand(canvasId, key);
        if (previous != null) {
            return replayPayload(previous, canvas.getVersion());
        }
        if (!canvas.getVersion().equals(req.canvasVersion())) {
            throw ApiException.conflict(ErrorCode.VERSION_CONFLICT, "画布版本已变化，请刷新后重试");
        }
        validate(req.assetType(), req.data());

        DramaAsset asset;
        if (req.assetId() != null) {
            asset = dramaAssetMapper.selectById(req.assetId());
            if (asset == null || !canvasId.equals(asset.getCanvasId())) {
                throw ApiException.notFound("短剧资产不存在");
            }
            if (!asset.getAssetType().equals(req.assetType())) {
                throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "短剧资产类型不可变更");
            }
            asset.setAssetData(writeJson(req.data()));
            asset.setAssetVersion(asset.getAssetVersion() + 1);
            asset.setUpdatedAt(OffsetDateTime.now());
        } else {
            asset = new DramaAsset();
            asset.setId(idGenerator.nextId());
            asset.setCanvasId(canvasId);
            asset.setAssetType(req.assetType());
            asset.setAssetData(writeJson(req.data()));
            asset.setAssetVersion(1);
            asset.setIdempotencyKey(key);
            asset.setCreatedAt(OffsetDateTime.now());
            asset.setUpdatedAt(OffsetDateTime.now());
        }

        int nextCanvasVersion = canvas.getVersion() + 1;
        asset.setCanvasVersion(nextCanvasVersion);
        try {
            if (req.assetId() == null) {
                dramaAssetMapper.insert(asset);
            } else {
                dramaAssetMapper.updateById(asset);
            }
        } catch (DuplicateKeyException e) {
            DramaAssetCommand duplicate = findCommand(canvasId, key);
            if (duplicate != null) {
                return replayPayload(duplicate, canvas.getVersion());
            }
            throw e;
        }

        canvas.setVersion(nextCanvasVersion);
        canvas.setUpdatedAt(OffsetDateTime.now());
        if (canvasMapper.updateById(canvas) == 0) {
            throw ApiException.conflict(ErrorCode.VERSION_CONFLICT, "画布已被并发更新，请刷新后重试");
        }
        DramaAssetCommand command = new DramaAssetCommand();
        command.setId(idGenerator.nextId());
        command.setCanvasId(canvasId);
        command.setIdempotencyKey(key);
        command.setAssetId(asset.getId());
        command.setAssetType(asset.getAssetType());
        command.setAssetVersion(asset.getAssetVersion());
        command.setResultCanvasVersion(nextCanvasVersion);
        command.setAssetDataSnapshot(asset.getAssetData());
        command.setCreatedAt(OffsetDateTime.now());
        dramaAssetCommandMapper.insert(command);
        return toPayload(asset, nextCanvasVersion, false);
    }

    public List<CanvasDtos.DramaAssetPayload> list(Long canvasId, String assetType,
                                                    String episodeId, String sceneId, String shotId) {
        Canvas canvas = canvasService.requireOwned(canvasId);
        if (assetType != null && !assetType.isBlank() && !ASSET_TYPES.contains(assetType)) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "未知短剧资产类型");
        }
        List<DramaAsset> assets = dramaAssetMapper.selectList(new LambdaQueryWrapper<DramaAsset>()
                .eq(DramaAsset::getCanvasId, canvasId)
                .eq(assetType != null && !assetType.isBlank(), DramaAsset::getAssetType, assetType)
                .orderByAsc(DramaAsset::getCreatedAt));
        return assets.stream()
                .filter(a -> matchesScope(readJson(a.getAssetData()), episodeId, sceneId, shotId))
                .map(a -> toPayload(a, canvas.getVersion(), false))
                .toList();
    }

    private DramaAssetCommand findCommand(Long canvasId, String key) {
        return dramaAssetCommandMapper.selectOne(new LambdaQueryWrapper<DramaAssetCommand>()
                .eq(DramaAssetCommand::getCanvasId, canvasId)
                .eq(DramaAssetCommand::getIdempotencyKey, key));
    }

    private String requireIdempotencyKey(String key) {
        if (key == null || key.isBlank() || key.length() > 128) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "写入短剧资产需要有效 Idempotency-Key");
        }
        return key.trim();
    }

    private void validate(String assetType, Map<String, Object> data) {
        if (!ASSET_TYPES.contains(assetType)) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "未知短剧资产类型");
        }
        if (data == null || data.isEmpty()) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "短剧资产 data 不能为空");
        }
        switch (assetType) {
            case "series_bible" -> requireText(data, "premise");
            case "episode" -> {
                requireNumber(data, "episodeNo", "episode_no");
                requireText(data, "goal");
            }
            case "scene" -> {
                requireNumber(data, "sceneOrder", "scene_order");
                requireText(data, "goal");
            }
            case "character_profile" -> {
                requireText(data, "name");
                requireText(data, "identityAnchor", "identity_anchor");
            }
            case "character_look" -> requireText(data, "characterId", "character_id");
            case "shot_spec" -> {
                requireNumber(data, "shotNo", "shot_no");
                requireText(data, "purpose");
            }
            case "continuity_constraint" -> {
                requireText(data, "subject");
                requireText(data, "rule");
            }
            case "audio_cue", "subtitle_cue" -> requireText(data, "text");
            default -> throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "未知短剧资产类型");
        }
    }

    private void requireText(Map<String, Object> data, String... keys) {
        for (String key : keys) {
            Object value = data.get(key);
            if (value != null && !value.toString().isBlank()) {
                return;
            }
        }
        throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "短剧资产缺少字段: " + keys[0]);
    }

    private void requireNumber(Map<String, Object> data, String... keys) {
        for (String key : keys) {
            if (data.get(key) instanceof Number) {
                return;
            }
        }
        throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "短剧资产缺少数值字段: " + keys[0]);
    }

    private boolean matchesScope(Map<String, Object> data, String episodeId, String sceneId, String shotId) {
        return matches(data, "episodeId", "episode_id", episodeId)
                && matches(data, "sceneId", "scene_id", sceneId)
                && matches(data, "shotId", "shot_id", shotId);
    }

    private boolean matches(Map<String, Object> data, String camel, String snake, String expected) {
        if (expected == null || expected.isBlank()) {
            return true;
        }
        Object actual = data.containsKey(camel) ? data.get(camel) : data.get(snake);
        return actual != null && expected.equals(actual.toString());
    }

    private String writeJson(Map<String, Object> data) {
        try {
            return objectMapper.writeValueAsString(data);
        } catch (Exception e) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "短剧资产 JSON 不可序列化");
        }
    }

    private Map<String, Object> readJson(String raw) {
        try {
            return objectMapper.readValue(raw == null ? "{}" : raw, new TypeReference<>() {});
        } catch (Exception e) {
            return Map.of();
        }
    }

    private CanvasDtos.DramaAssetPayload toPayload(DramaAsset asset, Integer currentCanvasVersion, boolean replayed) {
        return new CanvasDtos.DramaAssetPayload(asset.getId(), asset.getCanvasId(), asset.getAssetType(),
                asset.getAssetVersion(), asset.getCanvasVersion(), currentCanvasVersion, readJson(asset.getAssetData()),
                replayed, asset.getCreatedAt() == null ? null : asset.getCreatedAt().toString(),
                asset.getUpdatedAt() == null ? null : asset.getUpdatedAt().toString());
    }

    private CanvasDtos.DramaAssetPayload replayPayload(DramaAssetCommand command, Integer currentCanvasVersion) {
        return new CanvasDtos.DramaAssetPayload(command.getAssetId(), command.getCanvasId(), command.getAssetType(),
                command.getAssetVersion(), command.getResultCanvasVersion(), currentCanvasVersion,
                readJson(command.getAssetDataSnapshot()), true,
                command.getCreatedAt() == null ? null : command.getCreatedAt().toString(),
                command.getCreatedAt() == null ? null : command.getCreatedAt().toString());
    }
}
