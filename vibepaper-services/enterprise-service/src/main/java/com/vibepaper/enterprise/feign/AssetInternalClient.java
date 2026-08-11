package com.vibepaper.enterprise.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.util.List;
import java.util.Map;

@FeignClient(name = "asset-service", path = "/internal")
public interface AssetInternalClient {

    @GetMapping("/assets/enterprise/{enterpriseId}")
    List<Map<String, Object>> enterpriseAssets(@PathVariable("enterpriseId") Long enterpriseId);
}
