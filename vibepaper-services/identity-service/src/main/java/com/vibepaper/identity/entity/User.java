package com.vibepaper.identity.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("users")
public class User {
    @TableId(type = IdType.INPUT)
    private Long id;
    private String email;
    private String phone;
    private String passwordHash;
    private String nickname;
    private String avatarUrl;
    /** active / disabled / banned / deleted */
    private String status;
    /** user / ent_member / ent_admin / ent_owner / ops_admin / super_admin */
    private String role;
    private Long enterpriseId;
    private String inviteCode;
    private Long invitedBy;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
    private OffsetDateTime lastLoginAt;
}
