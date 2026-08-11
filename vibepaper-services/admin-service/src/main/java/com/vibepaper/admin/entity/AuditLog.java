package com.vibepaper.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.vibepaper.common.mybatis.JsonbTypeHandler;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("audit_logs")
public class AuditLog {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long operatorId;
    private String action;
    private String targetType;
    private Long targetId;
    @com.baomidou.mybatisplus.annotation.TableField(typeHandler = JsonbTypeHandler.class)
    private String beforeValue;
    @com.baomidou.mybatisplus.annotation.TableField(typeHandler = JsonbTypeHandler.class)
    private String afterValue;
    private String ip;
    private String requestId;
    private OffsetDateTime createdAt;
}
