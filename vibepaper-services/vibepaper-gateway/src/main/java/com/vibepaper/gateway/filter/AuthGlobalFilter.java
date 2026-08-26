package com.vibepaper.gateway.filter;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vibepaper.common.api.ErrorResponse;
import com.vibepaper.common.security.JwtUtil;
import io.jsonwebtoken.Claims;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;

/**
 * 网关统一鉴权：白名单放行；其余请求校验 Bearer JWT，撤销校验，透传 X-User-* 头。
 */
@Slf4j
@Component
public class AuthGlobalFilter implements GlobalFilter, Ordered {

    private static final AntPathMatcher MATCHER = new AntPathMatcher();
    /** 白名单：路径 + 允许的方法（null 表示全部方法）。 */
    private static final List<String[]> WHITELIST = List.of(
            new String[]{"/api/v1/auth/register", null},
            new String[]{"/api/v1/auth/login", null},
            new String[]{"/api/v1/auth/refresh", null},
            new String[]{"/api/v1/gallery/publications/**", "GET"},
            new String[]{"/api/v1/publications/*", "GET"},
            new String[]{"/api/v1/announcements", "GET"},
            new String[]{"/api/v1/announcements/**", "GET"},
            new String[]{"/api/v1/models/**", "GET"},
            // 画布 <img>/<video> 无法带 Authorization，输出/素材文件只读放行
            new String[]{"/api/v1/tasks/*/outputs/file/**", "GET"},
            new String[]{"/api/v1/assets/file", "GET"},
            new String[]{"/actuator/**", null},
            new String[]{"/v3/api-docs/**", null},
            new String[]{"/swagger-ui/**", null},
            new String[]{"/swagger-ui.html", null},
            new String[]{"/favicon.ico", null}
    );

    private final JwtUtil jwtUtil;
    private final ReactiveStringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public AuthGlobalFilter(JwtUtil jwtUtil, ReactiveStringRedisTemplate redis, ObjectMapper objectMapper) {
        this.jwtUtil = jwtUtil;
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getURI().getPath();
        String method = exchange.getRequest().getMethod().name();
        boolean whitelisted = false;
        for (String[] entry : WHITELIST) {
            if (MATCHER.match(entry[0], path) && (entry[1] == null || entry[1].equals(method))) {
                whitelisted = true;
                break;
            }
        }

        String auth = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        if (whitelisted) {
            // 公开接口：无 Token 直接放行；有 Token 则透传用户头（作者可看 pending 作品等）
            if (auth == null || !auth.startsWith("Bearer ")) {
                return chain.filter(exchange);
            }
            return attachUserHeaders(exchange, chain, auth.substring(7), true);
        }

        if (auth == null || !auth.startsWith("Bearer ")) {
            return reject(exchange, "AUTHENTICATION_REQUIRED", "请先登录", HttpStatus.UNAUTHORIZED, false);
        }
        return attachUserHeaders(exchange, chain, auth.substring(7), false);
    }

    private Mono<Void> attachUserHeaders(ServerWebExchange exchange, GatewayFilterChain chain,
                                         String token, boolean optional) {
        Claims claims;
        try {
            claims = jwtUtil.parse(token);
        } catch (Exception e) {
            if (optional) {
                return chain.filter(exchange);
            }
            return reject(exchange, "UNAUTHORIZED", "登录已过期，请重新登录", HttpStatus.UNAUTHORIZED, true);
        }
        String jti = claims.get("jti", String.class);
        return redis.hasKey("auth:revoked:" + jti)
                .flatMap(revoked -> {
                    if (Boolean.TRUE.equals(revoked)) {
                        if (optional) {
                            return chain.filter(exchange);
                        }
                        return reject(exchange, "UNAUTHORIZED", "登录已失效，请重新登录", HttpStatus.UNAUTHORIZED, false);
                    }
                    ServerHttpRequest mutated = exchange.getRequest().mutate()
                            .header("X-User-Id", claims.getSubject())
                            .header("X-User-Role", claims.get("role", String.class))
                            .header("X-Enterprise-Id", claims.get("ent", String.class) == null ? "" : claims.get("ent", String.class))
                            .header("X-Request-Id", UUID.randomUUID().toString().replace("-", ""))
                            .build();
                    return chain.filter(exchange.mutate().request(mutated).build());
                });
    }

    private Mono<Void> reject(ServerWebExchange exchange, String code, String message,
                              HttpStatus status, boolean retryable) {
        ErrorResponse body = ErrorResponse.of(code, message, null,
                UUID.randomUUID().toString().replace("-", ""), retryable);
        try {
            byte[] bytes = objectMapper.writeValueAsBytes(body);
            exchange.getResponse().setStatusCode(status);
            exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
            DataBuffer buffer = exchange.getResponse().bufferFactory().wrap(bytes);
            return exchange.getResponse().writeWith(Mono.just(buffer));
        } catch (Exception e) {
            exchange.getResponse().setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);
            return exchange.getResponse().setComplete();
        }
    }

    @Override
    public int getOrder() {
        return -100;
    }
}
