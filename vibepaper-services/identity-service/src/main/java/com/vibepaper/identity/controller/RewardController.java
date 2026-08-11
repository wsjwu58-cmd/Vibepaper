package com.vibepaper.identity.controller;

import com.vibepaper.identity.dto.RewardDtos;
import com.vibepaper.identity.service.RewardService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/rewards")
@RequiredArgsConstructor
public class RewardController {
    private final RewardService rewardService;

    @PostMapping("/checkin")
    public RewardDtos.CheckinResult checkin() {
        return rewardService.checkin();
    }

    @GetMapping("/daily-tasks")
    public List<RewardDtos.DailyTaskView> dailyTasks() {
        return rewardService.dailyTasks();
    }

    @PostMapping("/daily-tasks/{taskKey}/claim")
    public RewardDtos.DailyTaskView claim(@PathVariable String taskKey) {
        return rewardService.claim(taskKey);
    }
}
