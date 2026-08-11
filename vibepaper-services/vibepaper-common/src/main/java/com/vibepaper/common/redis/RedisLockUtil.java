package com.vibepaper.common.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

import java.time.Duration;
import java.util.Collections;
import java.util.UUID;

/**
 * 轻量 Redis 分布式锁：SET NX PX + Lua 释放（技术概要 §8.4）。
 */
public class RedisLockUtil {
    private static final DefaultRedisScript<Long> UNLOCK_SCRIPT = new DefaultRedisScript<>(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            Long.class);

    private final StringRedisTemplate redis;

    public RedisLockUtil(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean tryLock(String key, Duration ttl) {
        String token = UUID.randomUUID().toString();
        Boolean ok = redis.opsForValue().setIfAbsent(key, token, ttl);
        return Boolean.TRUE.equals(ok);
    }

    public void unlock(String key, String token) {
        redis.execute(UNLOCK_SCRIPT, Collections.singletonList(key), token);
    }
}
