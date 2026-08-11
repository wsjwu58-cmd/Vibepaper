package com.vibepaper.identity.controller;

import com.vibepaper.identity.dto.RewardDtos;
import com.vibepaper.identity.service.InviteService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/invites")
@RequiredArgsConstructor
public class InviteController {
    private final InviteService inviteService;

    @GetMapping("/me")
    public RewardDtos.InviteView myInvites() {
        return inviteService.myInvites();
    }

    @PostMapping("/accept")
    public Map<String, String> accept(@RequestBody Map<String, String> body) {
        inviteService.accept(body.get("inviteCode"));
        return Map.of("status", "ok");
    }
}
