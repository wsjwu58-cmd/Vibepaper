package com.vibepaper.admin.controller;

import com.vibepaper.admin.service.AdminService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 用户端公告（P1｜F-33）。
 */
@RestController
@RequiredArgsConstructor
public class AnnouncementController {
    private final AdminService adminService;

    @GetMapping("/api/v1/announcements")
    public List<Map<String, Object>> list() {
        return adminService.userAnnouncements();
    }

    @PostMapping("/api/v1/announcements/{id}/read")
    public Map<String, String> markRead(@PathVariable Long id) {
        adminService.markAnnouncementRead(id);
        return Map.of("status", "ok");
    }
}
