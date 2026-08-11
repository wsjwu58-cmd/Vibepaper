package com.vibepaper.enterprise.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@FeignClient(name = "billing-service", path = "/internal")
public interface BillingInternalClient {

    @PostMapping("/accounts")
    Map<String, Object> createAccount(@RequestBody Map<String, Object> body);

    @GetMapping("/accounts/{userId}")
    Map<String, Object> getAccount(@PathVariable("userId") Long userId);

    @PostMapping("/allocate")
    Map<String, String> allocate(@RequestBody Map<String, Object> body);

    @PostMapping("/recycle")
    Map<String, String> recycle(@RequestBody Map<String, Object> body);

    @PostMapping("/accounts/{userId}/credit")
    Map<String, Object> credit(@PathVariable("userId") Long userId, @RequestBody Map<String, Object> body);

    @PutMapping("/accounts/{userId}/enterprise")
    Map<String, Object> linkEnterprise(@PathVariable("userId") Long userId, @RequestBody Map<String, Object> body);

    @GetMapping("/enterprises/{enterpriseId}/usage")
    List<Map<String, Object>> enterpriseUsage(@PathVariable("enterpriseId") Long enterpriseId,
                                              @RequestParam(required = false) java.time.OffsetDateTime from,
                                              @RequestParam(required = false) java.time.OffsetDateTime to);

    @GetMapping("/accounts/{userId}/ledgers")
    List<Map<String, Object>> ledgers(@PathVariable("userId") Long userId);
}
