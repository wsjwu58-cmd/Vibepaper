package com.vibepaper.identity.controller;

import com.vibepaper.identity.dto.AuthDtos;
import com.vibepaper.identity.service.InternalService;
import com.vibepaper.identity.service.RewardService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 内部接口：仅服务间调用（网关不暴露 /internal）。
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalController {
    private final InternalService internalService;
    private final RewardService rewardService;

    @GetMapping("/users/{userId}")
    public AuthDtos.UserView getUser(@PathVariable Long userId) {
        return internalService.getUser(userId);
    }

    @GetMapping("/users/by-email")
    public AuthDtos.UserView getByEmail(@RequestParam String email) {
        return internalService.getByEmail(email);
    }

    @GetMapping("/users")
    public List<AuthDtos.UserView> listUsers(@RequestParam List<Long> ids) {
        return internalService.list(ids);
    }

    @GetMapping("/users/page")
    public Map<String, Object> pageUsers(@RequestParam(required = false) String keyword,
                                         @RequestParam(required = false) String status,
                                         @RequestParam(defaultValue = "1") int page,
                                         @RequestParam(defaultValue = "20") int pageSize) {
        return internalService.page(keyword, status, page, pageSize);
    }

    @PutMapping("/users/{userId}/status")
    public Map<String, String> updateStatus(@PathVariable Long userId, @RequestBody Map<String, String> body) {
        internalService.updateStatus(userId, body.get("status"));
        return Map.of("status", "ok");
    }

    @PostMapping("/users/{userId}/daily-task-progress")
    public Map<String, String> markTaskProgress(@PathVariable Long userId, @RequestBody Map<String, Object> body) {
        rewardService.markTaskProgress(userId, (String) body.get("taskKey"), ((Number) body.getOrDefault("delta", 1)).intValue());
        return Map.of("status", "ok");
    }
}
