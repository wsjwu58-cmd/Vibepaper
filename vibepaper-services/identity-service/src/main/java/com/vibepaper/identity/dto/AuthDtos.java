package com.vibepaper.identity.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class AuthDtos {
    private AuthDtos() {
    }

    public record RegisterRequest(
            @NotBlank @Email String email,
            @NotBlank @Size(min = 6, max = 64) String password,
            @NotBlank @Size(max = 64) String nickname,
            String inviteCode) {
    }

    public record LoginRequest(@NotBlank String account, @NotBlank String password) {
    }

    public record RefreshRequest(@NotBlank String refreshToken) {
    }

    public record TokenResponse(String accessToken, String refreshToken, String tokenType, long expiresIn,
                                UserView user) {
    }

    public record UserView(Long id, String email, String phone, String nickname, String avatarUrl,
                           String status, String role, Long enterpriseId, String inviteCode) {
    }

    public record UpdateProfileRequest(String nickname, String avatarUrl) {
    }

    public record PreferenceRequest(String theme, String language, String defaultTextModel,
                                    String defaultImageModel, String defaultVideoModel, String defaultResolution) {
    }
}
