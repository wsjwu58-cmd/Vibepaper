package com.vibepaper.identity.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

import java.util.Map;

@FeignClient(name = "billing-service", path = "/internal")
public interface BillingClient {

    @PostMapping("/accounts")
    Map<String, Object> createAccount(@RequestBody Map<String, Object> body);

    @GetMapping("/accounts/{userId}")
    Map<String, Object> getAccount(@PathVariable("userId") Long userId);

    @PostMapping("/accounts/{userId}/credit")
    Map<String, Object> credit(@PathVariable("userId") Long userId, @RequestBody Map<String, Object> body);
}
