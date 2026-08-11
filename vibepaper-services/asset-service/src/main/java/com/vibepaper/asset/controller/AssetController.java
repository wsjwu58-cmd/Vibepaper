package com.vibepaper.asset.controller;

import com.vibepaper.asset.dto.AssetDtos;
import com.vibepaper.asset.service.AssetService;
import com.vibepaper.common.api.PageResult;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/assets")
@RequiredArgsConstructor
public class AssetController {
    private final AssetService assetService;

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public AssetDtos.AssetView upload(@RequestParam("file") MultipartFile file,
                                      @RequestParam(required = false) String type,
                                      @RequestParam(required = false) Long canvasId,
                                      @RequestParam(required = false) Long nodeId) {
        return assetService.upload(file, type, canvasId, nodeId);
    }

    @GetMapping
    public PageResult<AssetDtos.AssetView> list(@RequestParam(defaultValue = "1") int page,
                                                @RequestParam(defaultValue = "50") int pageSize,
                                                @RequestParam(required = false) String type,
                                                @RequestParam(required = false) String keyword,
                                                @RequestParam(required = false) Long enterpriseId) {
        return assetService.list(page, pageSize, type, keyword, enterpriseId);
    }

    @GetMapping("/{assetId}")
    public AssetDtos.AssetView get(@PathVariable Long assetId) {
        return assetService.get(assetId);
    }

    @PutMapping("/{assetId}")
    public AssetDtos.AssetView rename(@PathVariable Long assetId, @RequestBody Map<String, String> body) {
        return assetService.rename(assetId, body.get("name"));
    }

    @PostMapping(value = "/{assetId}/replace", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public AssetDtos.AssetView replace(@PathVariable Long assetId, @RequestParam("file") MultipartFile file) {
        return assetService.replace(assetId, file);
    }

    @DeleteMapping("/{assetId}")
    public Map<String, Object> delete(@PathVariable Long assetId) {
        return assetService.delete(assetId);
    }

    @PostMapping("/{assetId}/references")
    public Map<String, String> addReference(@PathVariable Long assetId, @RequestBody Map<String, Object> body) {
        assetService.addReference(assetId,
                body.get("canvasId") == null ? null : ((Number) body.get("canvasId")).longValue(),
                body.get("nodeId") == null ? null : ((Number) body.get("nodeId")).longValue(),
                body.get("refType") == null ? "canvas" : body.get("refType").toString());
        return Map.of("status", "ok");
    }

    @PostMapping("/{assetId}/to-enterprise")
    public AssetDtos.AssetView toEnterprise(@PathVariable Long assetId, @RequestBody Map<String, Object> body) {
        return assetService.transferToEnterprise(assetId, ((Number) body.get("enterpriseId")).longValue());
    }

    @PostMapping("/{assetId}/certify")
    public AssetDtos.AssetView certify(@PathVariable Long assetId, @RequestBody Map<String, String> body) {
        return assetService.certify(assetId, body.get("status"), body.get("reason"));
    }

    @GetMapping("/file")
    public ResponseEntity<byte[]> content(@RequestParam String path) {
        byte[] bytes = assetService.readContent(path);
        MediaType mediaType = MediaType.APPLICATION_OCTET_STREAM;
        String lower = path == null ? "" : path.toLowerCase();
        if (lower.endsWith(".png")) mediaType = MediaType.IMAGE_PNG;
        else if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) mediaType = MediaType.IMAGE_JPEG;
        else if (lower.endsWith(".gif")) mediaType = MediaType.IMAGE_GIF;
        else if (lower.endsWith(".webp")) mediaType = MediaType.parseMediaType("image/webp");
        else if (lower.endsWith(".mp4")) mediaType = MediaType.parseMediaType("video/mp4");
        else if (lower.endsWith(".webm")) mediaType = MediaType.parseMediaType("video/webm");
        else if (lower.endsWith(".wav")) mediaType = MediaType.parseMediaType("audio/wav");
        else if (lower.endsWith(".mp3")) mediaType = MediaType.parseMediaType("audio/mpeg");
        return ResponseEntity.ok().contentType(mediaType).body(bytes);
    }
}
