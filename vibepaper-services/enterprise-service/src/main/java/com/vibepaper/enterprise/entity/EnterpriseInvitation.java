package com.vibepaper.enterprise.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("enterprise_invitations")
public class EnterpriseInvitation {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long enterpriseId;
    private String token;
    private Long inviterId;
    private String status;
    private OffsetDateTime expiresAt;
    private OffsetDateTime createdAt;
}
