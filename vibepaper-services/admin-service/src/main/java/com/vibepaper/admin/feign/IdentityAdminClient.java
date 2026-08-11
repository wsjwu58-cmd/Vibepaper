package com.vibepaper.admin.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@FeignClient(name = "identity-service", path = "/internal")
public interface IdentityAdminClient {

    @GetMapping("/users/page")
    Map<String, Object> pageUsers(@RequestParam(required = false) String keyword,
                                  @RequestParam(required = false) String status,
                                  @RequestParam(defaultValue = "1") int page,
                                  @RequestParam(defaultValue = "20") int pageSize);

    @GetMapping("/users/{userId}")
    Map<String, Object> getUser(@PathVariable("userId") Long userId);

    @PutMapping("/users/{userId}/status")
    Map<String, String> updateStatus(@PathVariable("userId") Long userId, @RequestBody Map<String, String> body);
}
