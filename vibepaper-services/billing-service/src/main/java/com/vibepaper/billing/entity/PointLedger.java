package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("point_ledgers")
public class PointLedger {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long userId;
    /** freeze / settle / unfreeze_settle / unfreeze_timeout / unfreeze_fail / unfreeze_cancel / recharge / allocate / recycle */
    private String ledgerType;
    /** in / out */
    private String direction;
    private Integer points;
    private Integer balanceAfter;
    private Long taskId;
    private Long orderId;
    private String reference;
    private OffsetDateTime createdAt;
}
