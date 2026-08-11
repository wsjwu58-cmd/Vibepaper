package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

@Data
@TableName("subscription_plans")
public class SubscriptionPlan {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String name;
    private Integer priceCny;
    @com.baomidou.mybatisplus.annotation.TableField(typeHandler = JsonbTypeHandler.class)
    private String benefits;
    private Boolean enabled;
}
