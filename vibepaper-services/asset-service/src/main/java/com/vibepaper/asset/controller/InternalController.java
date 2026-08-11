package com.vibepaper.asset.controller;

import com.vibepaper.asset.dto.AssetDtos;
import com.vibepaper.asset.entity.Asset;
import com.vibepaper.asset.service.AssetService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 内部接口：agent 搜索素材、企业素材库、admin 管理。
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalController {
    private final AssetService assetService;

    @GetMapping("/assets")
    public List<AssetDtos.AssetView> search(@RequestParam(required = false) String keyword,
                                            @RequestParam(required = false) String type,
                                            @RequestParam(required = false) Long enterpriseId) {
        return assetService.searchAssets(keyword, type, enterpriseId).stream().map(assetService::toView).toList();
    }

    @GetMapping("/assets/{assetId}")
    public Asset get(@PathVariable Long assetId) {
        return assetService.getById(assetId);
    }

    @GetMapping("/assets/enterprise/{enterpriseId}")
    public List<AssetDtos.AssetView> enterpriseAssets(@PathVariable Long enterpriseId) {
        return assetService.searchAssets(null, null, enterpriseId).stream().map(assetService::toView).toList();
    }
}
