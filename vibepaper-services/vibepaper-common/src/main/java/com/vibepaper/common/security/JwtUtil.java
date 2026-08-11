package com.vibepaper.common.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Map;
import java.util.UUID;

/**
 * JWT 签发与校验（HS256，access 15min / refresh 7d）。
 */
public class JwtUtil {
    private final SecretKey key;
    private final long accessTtlSeconds;
    private final long refreshTtlSeconds;

    public JwtUtil(String secret, long accessTtlSeconds, long refreshTtlSeconds) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.accessTtlSeconds = accessTtlSeconds;
        this.refreshTtlSeconds = refreshTtlSeconds;
    }

    public String createAccessToken(String userId, String role, String enterpriseId) {
        return createToken(userId, role, enterpriseId, accessTtlSeconds, "access");
    }

    public String createRefreshToken(String userId, String role, String enterpriseId) {
        return createToken(userId, role, enterpriseId, refreshTtlSeconds, "refresh");
    }

    private String createToken(String userId, String role, String enterpriseId, long ttlSeconds, String type) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(userId)
                .claims(Map.of("role", role == null ? "user" : role,
                        "ent", enterpriseId == null ? "" : enterpriseId,
                        "type", type,
                        "jti", UUID.randomUUID().toString().replace("-", "")))
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plusSeconds(ttlSeconds)))
                .signWith(key)
                .compact();
    }

    public Claims parse(String token) {
        return Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
    }

    public boolean isValid(String token) {
        try {
            parse(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
