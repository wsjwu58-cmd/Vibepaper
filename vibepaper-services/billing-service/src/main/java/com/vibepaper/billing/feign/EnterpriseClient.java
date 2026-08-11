package com.vibepaper.billing.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.util.Map;

@FeignClient(name = "enterprise-service", path = "/internal")
public interface EnterpriseClient {

    @GetMapping("/enterprises/{enterpriseId}/settings")
    Map<String, Object> getSettings(@PathVariable("enterpriseId") Long enterpriseId);
}
