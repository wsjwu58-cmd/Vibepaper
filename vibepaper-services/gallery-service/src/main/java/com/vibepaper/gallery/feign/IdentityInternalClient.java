package com.vibepaper.gallery.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.util.Map;

@FeignClient(name = "identity-service", path = "/internal")
public interface IdentityInternalClient {

    @GetMapping("/users/{userId}")
    Map<String, Object> getUser(@PathVariable("userId") Long userId);
}
