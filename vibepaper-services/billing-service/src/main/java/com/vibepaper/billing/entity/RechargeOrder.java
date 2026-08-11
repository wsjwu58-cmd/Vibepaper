package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("recharge_orders")
public class RechargeOrder {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long userId;
    private String orderNo;
    private Long packageId;
    private Integer points;
    private Integer amountCny;
    private String channel;
    /** pending / success / failed / refunded */
    private String status;
    private String idempotencyKey;
    private OffsetDateTime paidAt;
    private OffsetDateTime createdAt;
}
