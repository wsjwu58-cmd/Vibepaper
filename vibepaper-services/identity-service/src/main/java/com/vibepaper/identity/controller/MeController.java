package com.vibepaper.identity.controller;

import com.vibepaper.identity.dto.AuthDtos;
import com.vibepaper.identity.entity.UserPreference;
import com.vibepaper.identity.service.UserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/me")
@RequiredArgsConstructor
public class MeController {
    private final UserService userService;

    @GetMapping
    public Map<String, Object> me() {
        return userService.getMe();
    }

    @PutMapping
    public AuthDtos.UserView updateProfile(@Valid @RequestBody AuthDtos.UpdateProfileRequest req) {
        return userService.updateProfile(req);
    }

    @GetMapping("/preferences")
    public UserPreference preferences() {
        return userService.getPreference(com.vibepaper.common.context.RequestContext.userIdLong());
    }

    @PutMapping("/preferences")
    public UserPreference updatePreferences(@RequestBody AuthDtos.PreferenceRequest req) {
        return userService.updatePreference(req);
    }
}
