package com.vibepaper.enterprise.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import com.vibepaper.enterprise.entity.*;
import com.vibepaper.enterprise.feign.AssetInternalClient;
import com.vibepaper.enterprise.feign.BillingInternalClient;
import com.vibepaper.enterprise.feign.IdentityInternalClient;
import com.vibepaper.enterprise.mapper.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 企业中心核心服务（P1｜F-26~F-32 / B-31~B-37）。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class EnterpriseService {
    private static final SecureRandom RANDOM = new SecureRandom();

    private final EnterpriseMapper enterpriseMapper;
    private final EnterpriseMemberMapper memberMapper;
    private final EnterpriseInvitationMapper invitationMapper;
    private final AllocationRecordMapper allocationRecordMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final BillingInternalClient billingClient;
    private final IdentityInternalClient identityClient;
    private final AssetInternalClient assetClient;

    @Transactional
    public Map<String, Object> create(String name) {
        Long userId = RequestContext.userIdLong();
        Long existing = memberMapper.selectCount(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getUserId, userId));
        if (existing > 0) {
            throw new ApiException("DUPLICATE", "您已加入企业，无法重复创建");
        }
        Enterprise ent = new Enterprise();
        ent.setId(idGenerator.nextId());
        ent.setName(name);
        ent.setOwnerId(userId);
        ent.setEnterpriseCode(generateCode());
        ent.setTotalPoints(0);
        ent.setAllocatablePoints(0);
        ent.setSharedPoolEnabled(false);
        ent.setAdminCanViewContent(false);
        ent.setStatus("active");
        ent.setCreatedAt(OffsetDateTime.now());
        ent.setUpdatedAt(OffsetDateTime.now());
        enterpriseMapper.insert(ent);

        EnterpriseMember owner = new EnterpriseMember();
        owner.setEnterpriseId(ent.getId());
        owner.setUserId(userId);
        owner.setRole("owner");
        owner.setJoinedAt(OffsetDateTime.now());
        memberMapper.insert(owner);
        try {
            billingClient.createAccount(Map.of("userId", -ent.getId(), "initialPoints", 0));
            billingClient.linkEnterprise(userId, Map.of("enterpriseId", ent.getId()));
        } catch (Exception e) {
            log.warn("billing init failed for enterprise {}: {}", ent.getId(), e.getMessage());
        }
        return toView(ent);
    }

    public Map<String, Object> myEnterprise() {
        Long userId = RequestContext.userIdLong();
        EnterpriseMember membership = memberMapper.selectOne(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getUserId, userId));
        if (membership == null) {
            Map<String, Object> empty = new HashMap<>();
            empty.put("enterprise", null);
            return empty;
        }
        Enterprise ent = enterpriseMapper.selectById(membership.getEnterpriseId());
        Map<String, Object> view = toView(ent);
        try {
            Map<String, Object> account = billingClient.getAccount(-ent.getId());
            view.put("totalPoints", account.get("balance"));
            view.put("allocatablePoints", account.get("availablePoints"));
        } catch (Exception e) {
            log.warn("fetch enterprise account failed: {}", e.getMessage());
        }
        view.put("myRole", membership.getRole());
        return Map.of("enterprise", view);
    }

    @Transactional
    public EnterpriseInvitation createInvitation(Long enterpriseId) {
        requireRole(enterpriseId, java.util.Set.of("owner", "admin"));
        EnterpriseInvitation inv = new EnterpriseInvitation();
        inv.setId(idGenerator.nextId());
        inv.setEnterpriseId(enterpriseId);
        inv.setToken(UUID.randomUUID().toString().replace("-", ""));
        inv.setInviterId(RequestContext.userIdLong());
        inv.setStatus("pending");
        inv.setExpiresAt(OffsetDateTime.now().plusDays(7));
        inv.setCreatedAt(OffsetDateTime.now());
        invitationMapper.insert(inv);
        return inv;
    }

    @Transactional
    public void acceptInvitation(String token) {
        Long userId = RequestContext.userIdLong();
        EnterpriseInvitation inv = invitationMapper.selectOne(new LambdaQueryWrapper<EnterpriseInvitation>()
                .eq(EnterpriseInvitation::getToken, token));
        if (inv == null || !"pending".equals(inv.getStatus())) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "邀请链接无效或已失效");
        }
        if (inv.getExpiresAt().isBefore(OffsetDateTime.now())) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "邀请链接已过期");
        }
        Long existing = memberMapper.selectCount(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getUserId, userId));
        if (existing > 0) {
            throw new ApiException("DUPLICATE", "您已加入企业");
        }
        inv.setStatus("accepted");
        invitationMapper.updateById(inv);
        EnterpriseMember member = new EnterpriseMember();
        member.setEnterpriseId(inv.getEnterpriseId());
        member.setUserId(userId);
        member.setRole("member");
        member.setJoinedAt(OffsetDateTime.now());
        memberMapper.insert(member);
        try {
            billingClient.linkEnterprise(userId, Map.of("enterpriseId", inv.getEnterpriseId()));
        } catch (Exception e) {
            log.warn("link enterprise account failed: {}", e.getMessage());
        }
    }

    public List<Map<String, Object>> members(Long enterpriseId) {
        requireMember(enterpriseId);
        List<EnterpriseMember> members = memberMapper.selectList(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getEnterpriseId, enterpriseId));
        return members.stream().map(m -> {
            Map<String, Object> view = new HashMap<>();
            view.put("userId", m.getUserId());
            view.put("role", m.getRole());
            view.put("joinedAt", m.getJoinedAt());
            try {
                Map<String, Object> user = identityClient.getUser(m.getUserId());
                view.put("nickname", user.get("nickname"));
                view.put("email", user.get("email"));
                view.put("avatarUrl", user.get("avatarUrl"));
            } catch (Exception e) {
                view.put("nickname", "用户" + m.getUserId());
            }
            try {
                view.put("account", billingClient.getAccount(m.getUserId()));
            } catch (Exception e) {
                view.put("account", Map.of("balance", 0, "frozenPoints", 0, "availablePoints", 0));
            }
            return view;
        }).toList();
    }

    @Transactional
    public void allocate(Long enterpriseId, Long memberId, int amount) {
        requireRole(enterpriseId, java.util.Set.of("owner", "admin"));
        requireMemberOf(enterpriseId, memberId);
        billingClient.allocate(Map.of("enterpriseId", enterpriseId, "memberId", memberId, "amount", amount));
        AllocationRecord record = record(enterpriseId, memberId, "allocate", amount);
        log.info("allocate ent={} member={} amount={} operator={}", enterpriseId, memberId, amount, RequestContext.userIdLong());
    }

    @Transactional
    public void recycle(Long enterpriseId, Long memberId, int amount) {
        requireRole(enterpriseId, java.util.Set.of("owner", "admin"));
        requireMemberOf(enterpriseId, memberId);
        billingClient.recycle(Map.of("enterpriseId", enterpriseId, "memberId", memberId, "amount", amount));
        record(enterpriseId, memberId, "recycle", amount);
        log.info("recycle ent={} member={} amount={} operator={}", enterpriseId, memberId, amount, RequestContext.userIdLong());
    }

    @Transactional
    public void removeMember(Long enterpriseId, Long memberId) {
        requireRole(enterpriseId, java.util.Set.of("owner", "admin"));
        EnterpriseMember member = requireMemberOf(enterpriseId, memberId);
        if ("owner".equals(member.getRole())) {
            throw ApiException.forbidden("不能移出企业所有者");
        }
        // 可用点数回收回企业池（冻结部分保留至任务终态，见 PRD §9.2 建议）
        try {
            Map<String, Object> account = billingClient.getAccount(memberId);
            int available = ((Number) account.getOrDefault("availablePoints", 0)).intValue();
            if (available > 0) {
                billingClient.recycle(Map.of("enterpriseId", enterpriseId, "memberId", memberId, "amount", available));
                record(enterpriseId, memberId, "recycle", available);
            }
        } catch (Exception e) {
            log.warn("recycle on remove failed: {}", e.getMessage());
        }
        memberMapper.delete(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getEnterpriseId, enterpriseId)
                .eq(EnterpriseMember::getUserId, memberId));
    }

    public List<AllocationRecord> allocationRecords(Long enterpriseId, String search, int page, int pageSize) {
        requireRole(enterpriseId, java.util.Set.of("owner", "admin"));
        return allocationRecordMapper.selectList(new LambdaQueryWrapper<AllocationRecord>()
                .eq(AllocationRecord::getEnterpriseId, enterpriseId)
                .and(search != null && !search.isBlank(), w -> w
                        .like(AllocationRecord::getMemberId, search)
                        .or().like(AllocationRecord::getAllocType, search))
                .orderByDesc(AllocationRecord::getCreatedAt)
                .last("limit " + Math.min(pageSize, 500)));
    }

    public List<Map<String, Object>> usage(Long enterpriseId, String scope, OffsetDateTime from, OffsetDateTime to) {
        requireMember(enterpriseId);
        if ("personal".equals(scope)) {
            List<EnterpriseMember> members = memberMapper.selectList(new LambdaQueryWrapper<EnterpriseMember>()
                    .eq(EnterpriseMember::getEnterpriseId, enterpriseId));
            List<Map<String, Object>> result = new java.util.ArrayList<>();
            for (EnterpriseMember m : members) {
                try {
                    List<Map<String, Object>> ledgers = billingClient.ledgers(m.getUserId());
                    result.addAll(ledgers.stream()
                            .filter(l -> "settle".equals(l.get("ledgerType")))
                            .map(l -> Map.<String, Object>of(
                                    "date", l.get("createdAt").toString().substring(0, 10),
                                    "points", l.get("points"), "memberId", m.getUserId()))
                            .toList());
                } catch (Exception ignored) {
                }
            }
            return result;
        }
        return billingClient.enterpriseUsage(enterpriseId, from, to);
    }

    public List<Map<String, Object>> assets(Long enterpriseId) {
        requireMember(enterpriseId);
        return assetClient.enterpriseAssets(enterpriseId);
    }

    @Transactional
    public Map<String, Object> updateName(Long enterpriseId, String name) {
        requireRole(enterpriseId, java.util.Set.of("owner"));
        Enterprise ent = enterpriseMapper.selectById(enterpriseId);
        if (name != null && !name.isBlank()) {
            ent.setName(name);
            ent.setUpdatedAt(OffsetDateTime.now());
            enterpriseMapper.updateById(ent);
        }
        return toView(ent);
    }

    @Transactional
    public void dissolve(Long enterpriseId) {
        requireRole(enterpriseId, java.util.Set.of("owner"));
        Enterprise ent = enterpriseMapper.selectById(enterpriseId);
        ent.setStatus("dissolved");
        ent.setUpdatedAt(OffsetDateTime.now());
        enterpriseMapper.updateById(ent);
        memberMapper.delete(new LambdaQueryWrapper<EnterpriseMember>().eq(EnterpriseMember::getEnterpriseId, enterpriseId));
        log.info("enterprise dissolved id={} by user={}", enterpriseId, RequestContext.userIdLong());
    }

    public Map<String, Object> settings(Long enterpriseId) {
        Enterprise ent = enterpriseMapper.selectById(enterpriseId);
        if (ent == null) {
            throw ApiException.notFound("企业不存在");
        }
        return Map.of("sharedPoolEnabled", ent.getSharedPoolEnabled(),
                "adminCanViewContent", ent.getAdminCanViewContent());
    }

    private AllocationRecord record(Long enterpriseId, Long memberId, String type, int points) {
        AllocationRecord record = new AllocationRecord();
        record.setId(idGenerator.nextId());
        record.setEnterpriseId(enterpriseId);
        record.setOperatorId(RequestContext.userIdLong());
        record.setMemberId(memberId);
        record.setAllocType(type);
        record.setPoints(points);
        try {
            Map<String, Object> account = billingClient.getAccount(memberId);
            record.setBalanceAfter(((Number) account.getOrDefault("balance", 0)).intValue());
        } catch (Exception e) {
            record.setBalanceAfter(0);
        }
        record.setCreatedAt(OffsetDateTime.now());
        allocationRecordMapper.insert(record);
        return record;
    }

    private Map<String, Object> toView(Enterprise ent) {
        Map<String, Object> view = new HashMap<>();
        view.put("id", ent.getId());
        view.put("name", ent.getName());
        view.put("ownerId", ent.getOwnerId());
        view.put("enterpriseCode", ent.getEnterpriseCode());
        view.put("totalPoints", ent.getTotalPoints());
        view.put("allocatablePoints", ent.getAllocatablePoints());
        view.put("sharedPoolEnabled", ent.getSharedPoolEnabled());
        view.put("adminCanViewContent", ent.getAdminCanViewContent());
        view.put("status", ent.getStatus());
        return view;
    }

    private EnterpriseMember requireMemberOf(Long enterpriseId, Long userId) {
        EnterpriseMember member = memberMapper.selectOne(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getEnterpriseId, enterpriseId)
                .eq(EnterpriseMember::getUserId, userId));
        if (member == null) {
            throw ApiException.notFound("成员不在该企业中");
        }
        return member;
    }

    private void requireMember(Long enterpriseId) {
        Long userId = RequestContext.userIdLong();
        EnterpriseMember member = memberMapper.selectOne(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getEnterpriseId, enterpriseId)
                .eq(EnterpriseMember::getUserId, userId));
        if (member == null) {
            throw ApiException.forbidden("您不是该企业成员");
        }
    }

    private void requireRole(Long enterpriseId, java.util.Set<String> allowedRoles) {
        Long userId = RequestContext.userIdLong();
        EnterpriseMember member = memberMapper.selectOne(new LambdaQueryWrapper<EnterpriseMember>()
                .eq(EnterpriseMember::getEnterpriseId, enterpriseId)
                .eq(EnterpriseMember::getUserId, userId));
        if (member == null || !allowedRoles.contains(member.getRole())) {
            throw ApiException.forbidden("权限不足，需要 " + allowedRoles + " 角色");
        }
    }

    private String generateCode() {
        String chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        StringBuilder sb = new StringBuilder("ENT-");
        for (int i = 0; i < 8; i++) {
            sb.append(chars.charAt(RANDOM.nextInt(chars.length())));
        }
        return sb.toString();
    }

}
