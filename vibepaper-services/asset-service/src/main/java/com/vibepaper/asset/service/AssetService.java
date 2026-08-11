package com.vibepaper.asset.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.vibepaper.asset.dto.AssetDtos;
import com.vibepaper.asset.entity.Asset;
import com.vibepaper.asset.entity.AssetReference;
import com.vibepaper.asset.mapper.AssetMapper;
import com.vibepaper.asset.mapper.AssetReferenceMapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.api.PageResult;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import javax.imageio.ImageIO;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 素材服务（P0 基础 + P1 企业转入/Seedance 认证）。
 * 存储模式：local（默认）或 minio（预留 S3 协议）。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AssetService {
    private static final Set<String> ALLOWED_TYPES = Set.of("image", "video", "audio", "text");
    private static final long MAX_SIZE = 200L * 1024 * 1024;

    private final AssetMapper assetMapper;
    private final AssetReferenceMapper referenceMapper;
    private final SnowflakeIdGenerator idGenerator;

    @Value("${vibepaper.storage.mode:local}")
    private String storageMode;
    @Value("${vibepaper.storage.local-path:E:\\VibePaperProject\\data\\assets}")
    private String localPath;

    @Transactional
    public AssetDtos.AssetView upload(MultipartFile file, String assetType, Long canvasId, Long nodeId) {
        if (file == null || file.isEmpty()) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "文件为空");
        }
        if (file.getSize() > MAX_SIZE) {
            throw new ApiException(ErrorCode.FILE_TOO_LARGE, "文件超过 200MB 限制");
        }
        String detected = detectType(file);
        if (assetType != null && !ALLOWED_TYPES.contains(assetType)) {
            throw ApiException.badRequest(ErrorCode.FILE_TYPE_INVALID, "素材类型必须是 image/video/audio/text");
        }
        String finalType = assetType == null ? detected : assetType;
        if (!ALLOWED_TYPES.contains(finalType)) {
            throw new ApiException(ErrorCode.FILE_TYPE_INVALID, "不支持的文件类型: " + file.getContentType());
        }
        Long userId = RequestContext.userIdLong();
        Asset asset = new Asset();
        asset.setId(idGenerator.nextId());
        asset.setOwnerId(userId);
        asset.setName(file.getOriginalFilename() == null ? "素材" : file.getOriginalFilename());
        asset.setAssetType(finalType);
        asset.setMimeType(file.getContentType());
        asset.setSizeBytes(file.getSize());
        asset.setStatus("ready");
        asset.setCertificationStatus("none");
        asset.setDeleted(false);
        asset.setCreatedAt(OffsetDateTime.now());
        asset.setUpdatedAt(OffsetDateTime.now());

        String objectKey = "users/" + userId + "/uploads/" + asset.getId() + "/original";
        String url = saveFile(objectKey, file);
        asset.setStoragePath(objectKey);
        asset.setUrl(url);
        String thumbUrl = generateThumbnail(asset.getId(), finalType, file);
        if (thumbUrl != null) {
            asset.setThumbnailUrl(thumbUrl);
        }
        assetMapper.insert(asset);
        if (canvasId != null || nodeId != null) {
            addReference(asset.getId(), canvasId, nodeId, "canvas");
        }
        return toView(asset);
    }

    public PageResult<AssetDtos.AssetView> list(int page, int pageSize, String type, String keyword, Long enterpriseId) {
        Long userId = RequestContext.userIdLong();
        LambdaQueryWrapper<Asset> qw = new LambdaQueryWrapper<Asset>()
                .eq(Asset::getOwnerId, userId)
                .eq(type != null && !type.isBlank(), Asset::getAssetType, type)
                .eq(enterpriseId != null, Asset::getEnterpriseId, enterpriseId)
                .like(keyword != null && !keyword.isBlank(), Asset::getName, keyword)
                .orderByDesc(Asset::getCreatedAt);
        Page<Asset> p = assetMapper.selectPage(new Page<>(page, pageSize), qw);
        return PageResult.of(p.getRecords().stream().map(this::toView).toList(), p.getTotal(), page, pageSize);
    }

    public AssetDtos.AssetView get(Long assetId) {
        Asset asset = requireOwned(assetId);
        return toView(asset);
    }

    @Transactional
    public AssetDtos.AssetView rename(Long assetId, String name) {
        Asset asset = requireOwned(assetId);
        if (name == null || name.isBlank()) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "名称不能为空");
        }
        asset.setName(name);
        asset.setUpdatedAt(OffsetDateTime.now());
        assetMapper.updateById(asset);
        return toView(asset);
    }

    @Transactional
    public AssetDtos.AssetView replace(Long assetId, MultipartFile file) {
        Asset asset = requireOwned(assetId);
        if (file.getSize() > MAX_SIZE) {
            throw new ApiException(ErrorCode.FILE_TOO_LARGE, "文件超过 200MB 限制");
        }
        String objectKey = "users/" + asset.getOwnerId() + "/assets/" + asset.getId() + "/v" + System.currentTimeMillis();
        asset.setUrl(saveFile(objectKey, file));
        asset.setStoragePath(objectKey);
        asset.setMimeType(file.getContentType());
        asset.setSizeBytes(file.getSize());
        asset.setName(file.getOriginalFilename() == null ? asset.getName() : file.getOriginalFilename());
        String thumbUrl = generateThumbnail(asset.getId(), asset.getAssetType(), file);
        if (thumbUrl != null) {
            asset.setThumbnailUrl(thumbUrl);
        }
        asset.setUpdatedAt(OffsetDateTime.now());
        assetMapper.updateById(asset);
        return toView(asset);
    }

    @Transactional
    public Map<String, Object> delete(Long assetId) {
        Asset asset = requireOwned(assetId);
        List<AssetReference> refs = referenceMapper.selectList(new LambdaQueryWrapper<AssetReference>()
                .eq(AssetReference::getAssetId, assetId));
        Map<String, Object> impact = new HashMap<>();
        impact.put("references", refs.stream().map(r -> Map.of(
                "canvasId", r.getCanvasId(), "nodeId", r.getNodeId(), "type", r.getRefType())).toList());
        assetMapper.deleteById(assetId);
        impact.put("deletedAssetId", assetId);
        return impact;
    }

    @Transactional
    public void addReference(Long assetId, Long canvasId, Long nodeId, String refType) {
        AssetReference ref = new AssetReference();
        ref.setId(idGenerator.nextId());
        ref.setAssetId(assetId);
        ref.setCanvasId(canvasId);
        ref.setNodeId(nodeId);
        ref.setRefType(refType == null ? "canvas" : refType);
        ref.setCreatedAt(OffsetDateTime.now());
        referenceMapper.insert(ref);
    }

    @Transactional
    public AssetDtos.AssetView transferToEnterprise(Long assetId, Long enterpriseId) {
        Asset asset = requireOwned(assetId);
        if (enterpriseId == null) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "缺少企业 ID");
        }
        if (asset.getEnterpriseId() != null && asset.getEnterpriseId().equals(enterpriseId)) {
            throw new ApiException("DUPLICATE", "该素材已在企业素材库中");
        }
        // 复制一份到企业素材库（个人素材删除不影响企业副本，见飞书指南）
        Asset copy = new Asset();
        copy.setId(idGenerator.nextId());
        copy.setOwnerId(asset.getOwnerId());
        copy.setName(asset.getName());
        copy.setAssetType(asset.getAssetType());
        copy.setMimeType(asset.getMimeType());
        copy.setSizeBytes(asset.getSizeBytes());
        copy.setUrl(asset.getUrl());
        copy.setThumbnailUrl(asset.getThumbnailUrl());
        copy.setStoragePath(asset.getStoragePath());
        copy.setStatus("ready");
        copy.setEnterpriseId(enterpriseId);
        copy.setCertificationStatus(asset.getCertificationStatus());
        copy.setDeleted(false);
        copy.setCreatedAt(OffsetDateTime.now());
        copy.setUpdatedAt(OffsetDateTime.now());
        assetMapper.insert(copy);
        return toView(copy);
    }

    @Transactional
    public AssetDtos.AssetView certify(Long assetId, String status, String reason) {
        Asset asset = requireOwned(assetId);
        if (!Set.of("pending", "approved", "rejected").contains(status)) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "认证状态必须是 pending/approved/rejected");
        }
        asset.setCertificationStatus(status);
        asset.setCertificationReason(reason);
        asset.setUpdatedAt(OffsetDateTime.now());
        assetMapper.updateById(asset);
        return toView(asset);
    }

    public Asset requireOwned(Long assetId) {
        Asset asset = assetMapper.selectById(assetId);
        Long userId = RequestContext.userIdLong();
        if (asset == null) {
            throw ApiException.notFound("素材不存在");
        }
        boolean owner = asset.getOwnerId().equals(userId);
        boolean enterpriseMember = asset.getEnterpriseId() != null;
        if (!owner && !enterpriseMember) {
            throw ApiException.forbidden("无权访问该素材");
        }
        return asset;
    }

    public Asset getById(Long assetId) {
        return assetMapper.selectById(assetId);
    }

    public List<Asset> searchAssets(String keyword, String type, Long enterpriseId) {
        LambdaQueryWrapper<Asset> qw = new LambdaQueryWrapper<Asset>()
                .and(w -> w.eq(Asset::getOwnerId, RequestContext.userIdLong())
                        .or().eq(Asset::getEnterpriseId, enterpriseId != null ? enterpriseId : -1L))
                .like(keyword != null && !keyword.isBlank(), Asset::getName, keyword)
                .eq(type != null && !type.isBlank(), Asset::getAssetType, type)
                .orderByDesc(Asset::getCreatedAt).last("limit 50");
        return assetMapper.selectList(qw);
    }

    public AssetDtos.AssetView toView(Asset a) {
        return new AssetDtos.AssetView(a.getId(), a.getOwnerId(), a.getName(), a.getAssetType(), a.getMimeType(),
                a.getSizeBytes(), a.getUrl(), a.getThumbnailUrl(), a.getStatus(), a.getEnterpriseId(),
                a.getCertificationStatus(), a.getCertificationReason(),
                a.getCreatedAt() == null ? null : a.getCreatedAt().toString(),
                a.getUpdatedAt() == null ? null : a.getUpdatedAt().toString());
    }

    private String saveFile(String objectKey, MultipartFile file) {
        try {
            if ("minio".equals(storageMode)) {
                return "s3://" + objectKey; // MinIO 模式预留：预签名直传
            }
            Path dir = Path.of(localPath, objectKey.replace('/', java.io.File.separatorChar)).getParent();
            Files.createDirectories(dir);
            Path target = Path.of(localPath, objectKey.replace('/', java.io.File.separatorChar));
            file.transferTo(target.toFile());
            return "/api/v1/assets/file?path=" + java.net.URLEncoder.encode(objectKey, java.nio.charset.StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new RuntimeException("文件存储失败", e);
        }
    }

    public byte[] readContent(String objectKey) {
        try {
            Path target = Path.of(localPath, objectKey.replace('/', java.io.File.separatorChar));
            return Files.readAllBytes(target);
        } catch (IOException e) {
            throw ApiException.notFound("文件不存在");
        }
    }

    private String generateThumbnail(Long assetId, String assetType, MultipartFile file) {
        if (!"image".equals(assetType)) {
            return null;
        }
        try {
            BufferedImage src = ImageIO.read(new ByteArrayInputStream(file.getBytes()));
            if (src == null) {
                return null;
            }
            int w = Math.min(320, src.getWidth());
            int h = (int) (src.getHeight() * (w / (double) src.getWidth()));
            BufferedImage thumb = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
            Graphics2D g = thumb.createGraphics();
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.drawImage(src, 0, 0, w, h, null);
            g.dispose();
            String key = "users/" + RequestContext.userIdLong() + "/assets/" + assetId + "/thumb.jpg";
            Path dir = Path.of(localPath, key.replace('/', java.io.File.separatorChar)).getParent();
            Files.createDirectories(dir);
            ImageIO.write(thumb, "jpg", Path.of(localPath, key.replace('/', java.io.File.separatorChar)).toFile());
            return "/api/v1/assets/file?path=" + java.net.URLEncoder.encode(key, java.nio.charset.StandardCharsets.UTF_8);
        } catch (Exception e) {
            log.debug("thumbnail failed: {}", e.getMessage());
            return null;
        }
    }

    private String detectType(MultipartFile file) {
        String ct = file.getContentType() == null ? "" : file.getContentType();
        String name = file.getOriginalFilename() == null ? "" : file.getOriginalFilename().toLowerCase();
        if (ct.startsWith("image/") || name.endsWith(".png") || name.endsWith(".jpg") || name.endsWith(".jpeg")
                || name.endsWith(".webp") || name.endsWith(".gif")) {
            return "image";
        }
        if (ct.startsWith("video/") || name.endsWith(".mp4") || name.endsWith(".mov") || name.endsWith(".webm")) {
            return "video";
        }
        if (ct.startsWith("audio/") || name.endsWith(".mp3") || name.endsWith(".wav") || name.endsWith(".m4a")) {
            return "audio";
        }
        if (ct.startsWith("text/") || name.endsWith(".md") || name.endsWith(".txt")) {
            return "text";
        }
        return "unknown";
    }
}
