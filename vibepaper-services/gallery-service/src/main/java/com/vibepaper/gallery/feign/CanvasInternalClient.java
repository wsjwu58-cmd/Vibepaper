package com.vibepaper.gallery.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@FeignClient(name = "canvas-service", path = "/internal")
public interface CanvasInternalClient {

    @GetMapping("/canvases/{canvasId}/export")
    Map<String, Object> exportCanvas(@PathVariable("canvasId") Long canvasId);

    @PostMapping("/canvases/import")
    Map<String, Object> importCanvas(@RequestBody Map<String, Object> body);
}
