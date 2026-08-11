package com.vibepaper.billing.feign;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

import java.util.Map;

/**
 * 开发降级通道：MQ 不可用时直接调用 generation-service 内部接口创建任务。
 */
@FeignClient(name = "generation-service", path = "/internal")
public interface GenerationClient {

    @PostMapping("/tasks")
    Map<String, Object> createTask(@RequestBody Map<String, Object> body);

    @PostMapping("/tasks/cancel")
    Map<String, Object> cancelTask(@RequestBody Map<String, Object> body);
}
