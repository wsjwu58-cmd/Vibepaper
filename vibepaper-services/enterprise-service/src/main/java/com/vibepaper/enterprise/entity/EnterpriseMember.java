package com.vibepaper.enterprise.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("enterprise_members")
public class EnterpriseMember {
    private Long enterpriseId;
    private Long userId;
    /** member / admin / owner */
    private String role;
    private OffsetDateTime joinedAt;
}
