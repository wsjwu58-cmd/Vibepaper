package com.vibepaper.identity.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.identity.dto.RewardDtos;
import com.vibepaper.identity.entity.DailyCheckin;
import com.vibepaper.identity.entity.DailyTask;
import com.vibepaper.identity.entity.UserDailyTaskProgress;
import com.vibepaper.identity.mapper.DailyCheckinMapper;
import com.vibepaper.identity.mapper.DailyTaskMapper;
import com.vibepaper.identity.mapper.UserDailyTaskProgressMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 每日签到与每日任务（P1｜F-21/B-21）。
 * 奖励规则默认：签到基础 10 点 + 连续 (streak-1)*2 点（上限 30），待运营数值表替换。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RewardService {
    private final DailyCheckinMapper checkinMapper;
    private final DailyTaskMapper taskMapper;
    private final UserDailyTaskProgressMapper progressMapper;
    private final com.vibepaper.identity.feign.BillingClient billingClient;

    @Transactional
    public RewardDtos.CheckinResult checkin() {
        Long userId = RequestContext.userIdLong();
        LocalDate today = LocalDate.now();
        DailyCheckin exists = checkinMapper.selectOne(new LambdaQueryWrapper<DailyCheckin>()
                .eq(DailyCheckin::getUserId, userId).eq(DailyCheckin::getCheckinDate, today));
        if (exists != null) {
            throw new ApiException("DUPLICATE", "今日已签到");
        }
        DailyCheckin yesterday = checkinMapper.selectOne(new LambdaQueryWrapper<DailyCheckin>()
                .eq(DailyCheckin::getUserId, userId).eq(DailyCheckin::getCheckinDate, today.minusDays(1)));
        int streak = yesterday == null ? 1 : yesterday.getStreak() + 1;
        int reward = Math.min(30, 10 + (streak - 1) * 2);
        DailyCheckin checkin = new DailyCheckin();
        checkin.setUserId(userId);
        checkin.setCheckinDate(today);
        checkin.setStreak(streak);
        checkin.setRewardPoints(reward);
        checkinMapper.insert(checkin);
        try {
            billingClient.credit(userId, Map.of("points", reward, "reason", "每日签到奖励"));
        } catch (Exception e) {
            log.warn("checkin credit failed: {}", e.getMessage());
        }
        markTaskProgress(userId, "daily_checkin", 1);
        return new RewardDtos.CheckinResult(today, streak, reward);
    }

    public List<RewardDtos.DailyTaskView> dailyTasks() {
        Long userId = RequestContext.userIdLong();
        LocalDate today = LocalDate.now();
        return taskMapper.selectList(new LambdaQueryWrapper<DailyTask>().eq(DailyTask::getEnabled, true))
                .stream().map(task -> {
                    UserDailyTaskProgress p = progressMapper.selectOne(new LambdaQueryWrapper<UserDailyTaskProgress>()
                            .eq(UserDailyTaskProgress::getUserId, userId)
                            .eq(UserDailyTaskProgress::getTaskId, task.getId())
                            .eq(UserDailyTaskProgress::getTaskDate, today));
                    int progress = p == null ? 0 : p.getProgress();
                    boolean claimed = p != null && Boolean.TRUE.equals(p.getClaimed());
                    return new RewardDtos.DailyTaskView(task.getId(), task.getTaskKey(), task.getTitle(),
                            task.getDescription(), task.getTarget(), progress, task.getRewardPoints(),
                            claimed, progress >= task.getTarget());
                }).toList();
    }

    @Transactional
    public RewardDtos.DailyTaskView claim(String taskKey) {
        Long userId = RequestContext.userIdLong();
        LocalDate today = LocalDate.now();
        DailyTask task = taskMapper.selectOne(new LambdaQueryWrapper<DailyTask>().eq(DailyTask::getTaskKey, taskKey));
        if (task == null) {
            throw ApiException.notFound("任务不存在");
        }
        UserDailyTaskProgress p = progressMapper.selectOne(new LambdaQueryWrapper<UserDailyTaskProgress>()
                .eq(UserDailyTaskProgress::getUserId, userId)
                .eq(UserDailyTaskProgress::getTaskId, task.getId())
                .eq(UserDailyTaskProgress::getTaskDate, today));
        int progress = p == null ? 0 : p.getProgress();
        boolean claimed = p != null && Boolean.TRUE.equals(p.getClaimed());
        if (claimed) {
            throw new ApiException("DUPLICATE", "奖励已领取");
        }
        if (progress < task.getTarget()) {
            throw new ApiException("TASK_NOT_COMPLETED", "任务尚未完成");
        }
        if (p == null) {
            p = new UserDailyTaskProgress();
            p.setUserId(userId);
            p.setTaskId(task.getId());
            p.setTaskDate(today);
            p.setProgress(progress);
            p.setClaimed(true);
            progressMapper.insert(p);
        } else {
            p.setClaimed(true);
            progressMapper.updateById(p);
        }
        try {
            billingClient.credit(userId, Map.of("points", task.getRewardPoints(), "reason", "每日任务奖励:" + taskKey));
        } catch (Exception e) {
            log.warn("task reward credit failed: {}", e.getMessage());
        }
        return new RewardDtos.DailyTaskView(task.getId(), task.getTaskKey(), task.getTitle(), task.getDescription(),
                task.getTarget(), progress, task.getRewardPoints(), true, true);
    }

    @Transactional
    public void markTaskProgress(Long userId, String taskKey, int delta) {
        DailyTask task = taskMapper.selectOne(new LambdaQueryWrapper<DailyTask>().eq(DailyTask::getTaskKey, taskKey));
        if (task == null) {
            return;
        }
        LocalDate today = LocalDate.now();
        UserDailyTaskProgress p = progressMapper.selectOne(new LambdaQueryWrapper<UserDailyTaskProgress>()
                .eq(UserDailyTaskProgress::getUserId, userId)
                .eq(UserDailyTaskProgress::getTaskId, task.getId())
                .eq(UserDailyTaskProgress::getTaskDate, today));
        if (p == null) {
            p = new UserDailyTaskProgress();
            p.setUserId(userId);
            p.setTaskId(task.getId());
            p.setTaskDate(today);
            p.setProgress(Math.min(task.getTarget(), delta));
            p.setClaimed(false);
            progressMapper.insert(p);
        } else if (!Boolean.TRUE.equals(p.getClaimed())) {
            p.setProgress(Math.min(task.getTarget(), p.getProgress() + delta));
            progressMapper.updateById(p);
        }
    }
}
