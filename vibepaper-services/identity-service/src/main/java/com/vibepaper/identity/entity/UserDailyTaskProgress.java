package com.vibepaper.identity.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDate;

@Data
@TableName("user_daily_task_progress")
public class UserDailyTaskProgress {
    private Long userId;
    private Long taskId;
    private LocalDate taskDate;
    private Integer progress;
    private Boolean claimed;
}
