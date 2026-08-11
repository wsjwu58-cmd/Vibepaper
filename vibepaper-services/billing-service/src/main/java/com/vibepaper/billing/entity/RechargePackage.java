package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("recharge_packages")
public class RechargePackage {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String name;
    private Integer points;
    private Integer priceCny;
    private Integer validityDays;
    private Boolean enabled;
    private Integer priority;
    private OffsetDateTime createdAt;
}
