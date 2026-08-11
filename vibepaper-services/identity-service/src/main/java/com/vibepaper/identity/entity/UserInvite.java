package com.vibepaper.identity.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
@TableName("user_invites")
public class UserInvite {
    @TableId(type = IdType.INPUT)
    private Long id;
    private Long inviterId;
    private Long inviteeId;
    private Integer rewardPoints;
    private OffsetDateTime createdAt;
}
