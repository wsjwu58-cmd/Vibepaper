package com.vibepaper.identity.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("auth_sessions")
public class AuthSession {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long userId;
    private String refreshTokenHash;
    private String ip;
    private String userAgent;
    private OffsetDateTime expiresAt;
    private Boolean revoked;
    private OffsetDateTime createdAt;
}
