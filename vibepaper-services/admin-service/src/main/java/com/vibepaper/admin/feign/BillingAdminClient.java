package com.vibepaper.admin.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@FeignClient(name = "billing-service", path = "/internal")
public interface BillingAdminClient {

    @GetMapping("/transactions")
    List<Map<String, Object>> transactions(@RequestParam(required = false) String status);

    @GetMapping("/accounts/{userId}/ledgers")
    List<Map<String, Object>> ledgers(@PathVariable("userId") Long userId);

    @PostMapping("/packages")
    Map<String, Object> createPackage(@RequestBody Map<String, Object> body);

    @PutMapping("/packages/{packageId}")
    Map<String, Object> updatePackage(@PathVariable("packageId") Long packageId, @RequestBody Map<String, Object> body);

    @DeleteMapping("/packages/{packageId}")
    Map<String, String> deletePackage(@PathVariable("packageId") Long packageId);
}
