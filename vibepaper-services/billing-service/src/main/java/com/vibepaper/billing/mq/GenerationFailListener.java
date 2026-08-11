package com.vibepaper.billing.mq;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vibepaper.billing.service.PointService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
@RocketMQMessageListener(topic = "generation-task-failed", consumerGroup = "billing-consumer")
public class GenerationFailListener implements RocketMQListener<String> {
    private final PointService pointService;
    private final ObjectMapper objectMapper;

    @Override
    public void onMessage(String message) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = objectMapper.readValue(message, Map.class);
            Long taskId = Long.parseLong(payload.get("taskId").toString());
            String errorCode = payload.get("errorCode") == null ? "MODEL_UNAVAILABLE" : payload.get("errorCode").toString();
            pointService.unfreezeFail(taskId, errorCode);
        } catch (Exception e) {
            log.error("consume failed message failed: {}", message, e);
        }
    }
}
