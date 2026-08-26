package com.vibepaper.admin.feign;

import com.vibepaper.common.api.PageResult;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@FeignClient(name = "asset-service", path = "/internal")
public interface AssetAdminClient {

    @GetMapping("/assets/admin")
    PageResult<Map<String, Object>> listAssets(@RequestParam(defaultValue = "1") int page,
                                               @RequestParam(defaultValue = "20") int pageSize,
                                               @RequestParam(required = false) String type,
                                               @RequestParam(required = false) String keyword,
                                               @RequestParam(required = false) String status);

    @PostMapping("/assets/{assetId}/moderate")
    Map<String, Object> moderate(@PathVariable("assetId") Long assetId, @RequestBody Map<String, String> body);
}
