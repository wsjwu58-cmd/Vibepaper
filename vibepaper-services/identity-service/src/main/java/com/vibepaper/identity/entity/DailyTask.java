package com.vibepaper.identity.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("daily_tasks")
public class DailyTask {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String taskKey;
    private String title;
    private String description;
    private Integer target;
    private Integer rewardPoints;
    private Boolean enabled;
}
