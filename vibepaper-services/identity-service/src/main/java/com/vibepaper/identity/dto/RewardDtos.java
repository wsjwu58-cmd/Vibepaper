package com.vibepaper.identity.dto;

import java.time.LocalDate;

public final class RewardDtos {
    private RewardDtos() {
    }

    public record CheckinResult(LocalDate date, int streak, int rewardPoints) {
    }

    public record DailyTaskView(Long id, String taskKey, String title, String description,
                                int target, int progress, int rewardPoints, boolean claimed, boolean completed) {
    }

    public record InviteView(String inviteCode, String inviteLink, int invitedCount,
                             java.util.List<InviteRecord> records) {
    }

    public record InviteRecord(Long inviteeId, String inviteeNickname, int rewardPoints,
                               java.time.OffsetDateTime createdAt) {
    }
}
