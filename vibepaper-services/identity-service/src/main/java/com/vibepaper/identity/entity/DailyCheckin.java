package com.vibepaper.identity.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDate;

@Data
@TableName("daily_checkins")
public class DailyCheckin {
    private Long userId;
    private LocalDate checkinDate;
    private Integer streak;
    private Integer rewardPoints;
}
