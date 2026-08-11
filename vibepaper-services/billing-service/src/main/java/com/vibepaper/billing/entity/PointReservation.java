package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("point_reservations")
public class PointReservation {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long userId;
    /** 实际持有冻结点数的账户（用户本人或企业池账户） */
    private Long accountOwnerId;
    private Long taskId;
    private Integer estimatedCost;
    /** pending / settled / expired / cancelled / refunded */
    private String status;
    private OffsetDateTime freezeDeadline;
    private OffsetDateTime createdAt;
    private OffsetDateTime settledAt;
}
