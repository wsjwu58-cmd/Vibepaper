package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("user_subscriptions")
public class UserSubscription {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long userId;
    private Long planId;
    private String status;
    private OffsetDateTime startedAt;
    private OffsetDateTime expiresAt;
}
