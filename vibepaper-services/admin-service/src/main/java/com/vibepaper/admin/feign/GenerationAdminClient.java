package com.vibepaper.admin.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@FeignClient(name = "generation-service", path = "/internal")
public interface GenerationAdminClient {

    @GetMapping("/models")
    Map<String, Object> listModels(@RequestParam(required = false) String type);

    @PostMapping("/models")
    Map<String, Object> createModel(@RequestBody Map<String, Object> body);

    @PutMapping("/models/{modelId}")
    Map<String, Object> updateModel(@PathVariable("modelId") Long modelId, @RequestBody Map<String, Object> body);

    @DeleteMapping("/models/{modelId}")
    Map<String, String> deleteModel(@PathVariable("modelId") Long modelId);

    @PutMapping("/models/{modelId}/pricing")
    Map<String, Object> updatePricing(@PathVariable("modelId") Long modelId, @RequestBody Map<String, Object> body);
}
