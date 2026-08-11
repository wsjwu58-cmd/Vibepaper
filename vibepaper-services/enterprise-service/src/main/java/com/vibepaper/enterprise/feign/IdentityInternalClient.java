package com.vibepaper.enterprise.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@FeignClient(name = "identity-service", path = "/internal")
public interface IdentityInternalClient {

    @GetMapping("/users/{userId}")
    Map<String, Object> getUser(@PathVariable("userId") Long userId);

    @PutMapping("/users/{userId}/status")
    Map<String, String> updateStatus(@PathVariable("userId") Long userId, @RequestBody Map<String, String> body);
}
