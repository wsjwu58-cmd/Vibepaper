package com.vibepaper.identity.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.Map;

@FeignClient(name = "canvas-service", path = "/internal")
public interface CanvasClient {

    @PostMapping("/canvases/default")
    Map<String, Object> createDefaultCanvas(@RequestParam("userId") Long userId,
                                            @RequestParam("nickname") String nickname);
}
