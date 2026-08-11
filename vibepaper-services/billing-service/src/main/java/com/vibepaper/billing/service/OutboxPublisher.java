package com.vibepaper.billing.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.billing.entity.OutboxEvent;
import com.vibepaper.billing.mapper.OutboxEventMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * Outbox Publisher：事务提交后扫描 outbox_events 投递 RocketMQ（技术概要 §9.3.2）。
 * MQ 不可用时若开启 direct-fallback 则直接调用 generation-service 内部接口，保证开发链路可跑通。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OutboxPublisher {
    private final OutboxEventMapper outboxMapper;
    private final RocketMQTemplate rocketMQTemplate;
    private final com.vibepaper.billing.feign.GenerationClient generationClient;
    private final ObjectMapper objectMapper;

    @Value("${vibepaper.mq.direct-fallback:false}")
    private boolean directFallback;

    @Scheduled(fixedDelay = 3000, initialDelay = 10000)
    public void publishPending() {
        List<OutboxEvent> events = outboxMapper.selectList(new LambdaQueryWrapper<OutboxEvent>()
                .eq(OutboxEvent::getStatus, "pending").orderByAsc(OutboxEvent::getCreatedAt).last("limit 50"));
        for (OutboxEvent event : events) {
            try {
                if (directFallback) {
                    directDispatch(event);
                } else {
                    rocketMQTemplate.syncSend(event.getEventType(), event.getPayload(), 3000);
                }
                event.setStatus("published");
                event.setPublishedAt(OffsetDateTime.now());
                outboxMapper.updateById(event);
            } catch (Exception e) {
                log.warn("outbox publish failed event={} id={} err={}", event.getEventType(), event.getId(), e.getMessage());
            }
        }
    }

    private void directDispatch(OutboxEvent event) {
        Map<String, Object> payload = parse(event.getPayload());
        switch (event.getEventType()) {
            case "generation-task-created" -> generationClient.createTask(payload);
            case "generation-task-cancelled" -> generationClient.cancelTask(payload);
            case "generation-task-expired" -> generationClient.cancelTask(
                    Map.of("taskId", payload.get("taskId"), "reason", "expired"));
            default -> throw new IllegalStateException("unsupported event: " + event.getEventType());
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parse(String json) {
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
