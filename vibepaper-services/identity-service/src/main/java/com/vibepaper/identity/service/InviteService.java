package com.vibepaper.identity.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import com.vibepaper.identity.dto.RewardDtos;
import com.vibepaper.identity.entity.User;
import com.vibepaper.identity.entity.UserInvite;
import com.vibepaper.identity.mapper.UserInviteMapper;
import com.vibepaper.identity.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 邀请中心（P1｜F-22/B-22）。
 */
@Service
@RequiredArgsConstructor
public class InviteService {
    private final UserMapper userMapper;
    private final UserInviteMapper inviteMapper;
    private final SnowflakeIdGenerator idGenerator;

    public RewardDtos.InviteView myInvites() {
        Long userId = RequestContext.userIdLong();
        User user = userMapper.selectById(userId);
        List<UserInvite> invites = inviteMapper.selectList(new LambdaQueryWrapper<UserInvite>()
                .eq(UserInvite::getInviterId, userId).orderByDesc(UserInvite::getCreatedAt));
        List<RewardDtos.InviteRecord> records = invites.stream().map(inv -> {
            User invitee = userMapper.selectById(inv.getInviteeId());
            return new RewardDtos.InviteRecord(inv.getInviteeId(),
                    invitee == null ? "已注销用户" : invitee.getNickname(),
                    inv.getRewardPoints(), inv.getCreatedAt());
        }).toList();
        return new RewardDtos.InviteView(user.getInviteCode(),
                "https://vibepaper.local/invite/" + user.getInviteCode(), records.size(), records);
    }

    public void accept(String inviteCode) {
        Long userId = RequestContext.userIdLong();
        User inviter = userMapper.selectOne(new LambdaQueryWrapper<User>().eq(User::getInviteCode, inviteCode));
        if (inviter == null) {
            throw ApiException.badRequest("INVALID_INPUT", "邀请码不存在");
        }
        User self = userMapper.selectById(userId);
        if (self.getInvitedBy() != null) {
            throw new ApiException("DUPLICATE", "已接受过邀请");
        }
        if (inviter.getId().equals(userId)) {
            throw ApiException.badRequest("INVALID_INPUT", "不能接受自己的邀请");
        }
        self.setInvitedBy(inviter.getId());
        userMapper.updateById(self);
        UserInvite invite = new UserInvite();
        invite.setId(idGenerator.nextId());
        invite.setInviterId(inviter.getId());
        invite.setInviteeId(userId);
        invite.setRewardPoints(100);
        invite.setCreatedAt(java.time.OffsetDateTime.now());
        inviteMapper.insert(invite);
    }
}
