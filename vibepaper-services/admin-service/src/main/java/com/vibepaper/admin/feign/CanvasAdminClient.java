package com.vibepaper.admin.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.Map;

@FeignClient(name = "canvas-service", path = "/internal")
public interface CanvasAdminClient {

    @GetMapping("/canvases/owner/{ownerId}/count")
    Map<String, Object> canvasCount(@PathVariable("ownerId") Long ownerId);
}
