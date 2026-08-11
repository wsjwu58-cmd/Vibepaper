package com.vibepaper.common.id;

/**
 * Snowflake 全局唯一 ID（AGENTS.md / Spec §2.5：ID 策略采用 Snowflake）。
 * 64-bit: 1 sign + 41 timestamp + 5 datacenter + 5 worker + 12 sequence。
 */
public class SnowflakeIdGenerator {
    private static final long EPOCH = 1735689600000L; // 2025-01-01T00:00:00Z
    private static final long DATACENTER_BITS = 5L;
    private static final long WORKER_BITS = 5L;
    private static final long SEQUENCE_BITS = 12L;
    private static final long MAX_DATACENTER = ~(-1L << DATACENTER_BITS);
    private static final long MAX_WORKER = ~(-1L << WORKER_BITS);
    private static final long MAX_SEQUENCE = ~(-1L << SEQUENCE_BITS);
    private static final long WORKER_SHIFT = SEQUENCE_BITS;
    private static final long DATACENTER_SHIFT = SEQUENCE_BITS + WORKER_BITS;
    private static final long TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_BITS + DATACENTER_BITS;

    private final long datacenterId;
    private final long workerId;
    private long sequence = 0L;
    private long lastTimestamp = -1L;

    public SnowflakeIdGenerator(long datacenterId, long workerId) {
        if (datacenterId > MAX_DATACENTER || datacenterId < 0) {
            throw new IllegalArgumentException("datacenterId out of range");
        }
        if (workerId > MAX_WORKER || workerId < 0) {
            throw new IllegalArgumentException("workerId out of range");
        }
        this.datacenterId = datacenterId;
        this.workerId = workerId;
    }

    public synchronized long nextId() {
        long timestamp = System.currentTimeMillis();
        if (timestamp < lastTimestamp) {
            timestamp = lastTimestamp;
        }
        if (timestamp == lastTimestamp) {
            sequence = (sequence + 1) & MAX_SEQUENCE;
            if (sequence == 0) {
                timestamp = tilNextMillis(lastTimestamp);
            }
        } else {
            sequence = 0L;
        }
        lastTimestamp = timestamp;
        return ((timestamp - EPOCH) << TIMESTAMP_SHIFT)
                | (datacenterId << DATACENTER_SHIFT)
                | (workerId << WORKER_SHIFT)
                | sequence;
    }

    private long tilNextMillis(long last) {
        long t = System.currentTimeMillis();
        while (t <= last) {
            t = System.currentTimeMillis();
        }
        return t;
    }
}
