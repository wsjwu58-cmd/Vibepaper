package com.vibepaper.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("analytics_events")
public class AnalyticsEvent {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String eventName;
    @com.baomidou.mybatisplus.annotation.TableField(typeHandler = JsonbTypeHandler.class)
    private String payload;
    private OffsetDateTime createdAt;
}
