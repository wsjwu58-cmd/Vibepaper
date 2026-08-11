package com.vibepaper.identity.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import com.vibepaper.common.security.JwtUtil;
import com.vibepaper.identity.dto.AuthDtos;
import com.vibepaper.identity.entity.AuthSession;
import com.vibepaper.identity.entity.User;
import com.vibepaper.identity.mapper.AuthSessionMapper;
import com.vibepaper.identity.mapper.UserMapper;
import io.jsonwebtoken.Claims;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthService {
    private static final BCryptPasswordEncoder ENCODER = new BCryptPasswordEncoder();
    private static final SecureRandom RANDOM = new SecureRandom();

    private final UserMapper userMapper;
    private final AuthSessionMapper sessionMapper;
    private final com.vibepaper.identity.mapper.UserInviteMapper inviteMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final JwtUtil jwtUtil;
    private final StringRedisTemplate redis;
    private final com.vibepaper.identity.feign.CanvasClient canvasClient;
    private final com.vibepaper.identity.feign.BillingClient billingClient;

    @Transactional
    public AuthDtos.TokenResponse register(AuthDtos.RegisterRequest req) {
        String email = req.email().toLowerCase().trim();
        Long exists = userMapper.selectCount(new LambdaQueryWrapper<User>().eq(User::getEmail, email));
        if (exists > 0) {
            throw new ApiException(ErrorCode.DUPLICATE, "该邮箱已注册");
        }
        User user = new User();
        user.setId(idGenerator.nextId());
        user.setEmail(email);
        user.setPasswordHash(ENCODER.encode(req.password()));
        user.setNickname(req.nickname());
        user.setStatus("active");
        user.setRole("user");
        user.setInviteCode(generateInviteCode());
        user.setCreatedAt(OffsetDateTime.now());
        user.setUpdatedAt(OffsetDateTime.now());
        userMapper.insert(user);

        // 绑定邀请关系并发放奖励
        if (req.inviteCode() != null && !req.inviteCode().isBlank()) {
            bindInvite(user, req.inviteCode().trim());
        }

        // 初始化计费账户与默认画布（外部服务，失败不影响注册主链路）
        try {
            billingClient.createAccount(Map.of("userId", user.getId(), "initialPoints", 0));
        } catch (Exception e) {
            log.warn("create billing account failed for user {}: {}", user.getId(), e.getMessage());
        }
        try {
            canvasClient.createDefaultCanvas(user.getId(), user.getNickname());
        } catch (Exception e) {
            log.warn("create default canvas failed for user {}: {}", user.getId(), e.getMessage());
        }

        AuthDtos.TokenResponse tokens = issueTokens(user);
        log.info("user registered user_id={} email={}", user.getId(), email);
        return tokens;
    }

    @Transactional
    public AuthDtos.TokenResponse login(AuthDtos.LoginRequest req) {
        String account = req.account().trim().toLowerCase();
        User user = userMapper.selectOne(new LambdaQueryWrapper<User>()
                .eq(User::getEmail, account).or().eq(User::getPhone, account));
        if (user == null || !ENCODER.matches(req.password(), user.getPasswordHash())) {
            throw ApiException.unauthorized("邮箱/手机号或密码错误");
        }
        if ("disabled".equals(user.getStatus()) || "banned".equals(user.getStatus())) {
            throw ApiException.forbidden("账号已被禁用或封禁");
        }
        if ("deleted".equals(user.getStatus())) {
            throw ApiException.notFound("账号不存在");
        }
        user.setLastLoginAt(OffsetDateTime.now());
        userMapper.updateById(user);
        log.info("user login user_id={}", user.getId());
        return issueTokens(user);
    }

    @Transactional
    public AuthDtos.TokenResponse refresh(String refreshToken) {
        Claims claims;
        try {
            claims = jwtUtil.parse(refreshToken);
        } catch (Exception e) {
            throw ApiException.unauthorized("刷新令牌无效或已过期");
        }
        if (!"refresh".equals(claims.get("type", String.class))) {
            throw ApiException.unauthorized("令牌类型错误");
        }
        Long userId = Long.parseLong(claims.getSubject());
        String tokenHash = sha256(refreshToken);
        AuthSession session = sessionMapper.selectOne(new LambdaQueryWrapper<AuthSession>()
                .eq(AuthSession::getUserId, userId)
                .eq(AuthSession::getRefreshTokenHash, tokenHash));
        if (session == null || Boolean.TRUE.equals(session.getRevoked())) {
            throw ApiException.unauthorized("刷新令牌已失效");
        }
        if (session.getExpiresAt().isBefore(OffsetDateTime.now())) {
            throw ApiException.unauthorized("刷新令牌已过期");
        }
        session.setRevoked(true);
        sessionMapper.updateById(session);
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw ApiException.notFound("用户不存在");
        }
        return issueTokens(user);
    }

    @Transactional
    public void logout(String accessToken) {
        Claims claims;
        try {
            claims = jwtUtil.parse(accessToken);
        } catch (Exception e) {
            throw ApiException.unauthorized("令牌无效");
        }
        String jti = claims.get("jti", String.class);
        if (jti != null) {
            redis.opsForValue().set("auth:revoked:" + jti, "1", Duration.ofSeconds(900));
        }
        Long userId = Long.parseLong(claims.getSubject());
        AuthSession session = sessionMapper.selectOne(new LambdaQueryWrapper<AuthSession>()
                .eq(AuthSession::getUserId, userId).eq(AuthSession::getRevoked, false)
                .orderByDesc(AuthSession::getCreatedAt).last("limit 1"));
        if (session != null) {
            session.setRevoked(true);
            sessionMapper.updateById(session);
        }
        log.info("user logout user_id={}", userId);
    }

    private AuthDtos.TokenResponse issueTokens(User user) {
        String enterpriseId = user.getEnterpriseId() == null ? "" : user.getEnterpriseId().toString();
        String access = jwtUtil.createAccessToken(user.getId().toString(), user.getRole(), enterpriseId);
        String refresh = jwtUtil.createRefreshToken(user.getId().toString(), user.getRole(), enterpriseId);
        AuthSession session = new AuthSession();
        session.setId(idGenerator.nextId());
        session.setUserId(user.getId());
        session.setRefreshTokenHash(sha256(refresh));
        session.setExpiresAt(OffsetDateTime.now().plusDays(7));
        session.setRevoked(false);
        session.setCreatedAt(OffsetDateTime.now());
        sessionMapper.insert(session);
        return new AuthDtos.TokenResponse(access, refresh, "Bearer", 900, toView(user));
    }

    private void bindInvite(User newUser, String inviteCode) {
        User inviter = userMapper.selectOne(new LambdaQueryWrapper<User>().eq(User::getInviteCode, inviteCode));
        if (inviter == null) {
            return; // 无效邀请码静默忽略
        }
        if (inviter.getId().equals(newUser.getId())) {
            return;
        }
        newUser.setInvitedBy(inviter.getId());
        userMapper.updateById(newUser);
        com.vibepaper.identity.entity.UserInvite invite = new com.vibepaper.identity.entity.UserInvite();
        invite.setId(idGenerator.nextId());
        invite.setInviterId(inviter.getId());
        invite.setInviteeId(newUser.getId());
        invite.setRewardPoints(100);
        invite.setCreatedAt(OffsetDateTime.now());
        inviteMapper.insert(invite);
        try {
            billingClient.credit(inviter.getId(), Map.of("points", 100, "reason", "邀请奖励"));
            billingClient.credit(newUser.getId(), Map.of("points", 50, "reason", "接受邀请奖励"));
        } catch (Exception e) {
            log.warn("invite reward credit failed: {}", e.getMessage());
        }
    }

    public static String sha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private String generateInviteCode() {
        String chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 8; i++) {
            sb.append(chars.charAt(RANDOM.nextInt(chars.length())));
        }
        return sb.toString();
    }

    public static AuthDtos.UserView toView(User user) {
        return new AuthDtos.UserView(user.getId(), user.getEmail(), user.getPhone(), user.getNickname(),
                user.getAvatarUrl(), user.getStatus(), user.getRole(), user.getEnterpriseId(), user.getInviteCode());
    }
}
