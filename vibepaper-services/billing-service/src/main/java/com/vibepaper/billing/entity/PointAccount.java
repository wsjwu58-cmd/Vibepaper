package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("point_accounts")
public class PointAccount {
    @TableId(type = IdType.INPUT)
    private Long userId;
    /** user / enterprise */
    private String ownerType;
    private Long enterpriseId;
    private Integer balance;
    private Integer frozenPoints;
    private String status;
    private OffsetDateTime updatedAt;

    public int available() {
        return balance - frozenPoints;
    }
}
