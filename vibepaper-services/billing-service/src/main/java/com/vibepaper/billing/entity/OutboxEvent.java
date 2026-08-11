package com.vibepaper.billing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("outbox_events")
public class OutboxEvent {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String eventType;
    @com.baomidou.mybatisplus.annotation.TableField(typeHandler = JsonbTypeHandler.class)
    private String payload;
    /** pending / published / failed */
    private String status;
    private String idempotencyKey;
    private OffsetDateTime createdAt;
    private OffsetDateTime publishedAt;
}
