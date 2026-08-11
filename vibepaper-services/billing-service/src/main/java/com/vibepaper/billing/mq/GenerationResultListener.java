package com.vibepaper.billing.mq;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vibepaper.billing.service.PointService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * 消费 generation-service 的任务结果消息，完成结算/解冻（BILL-03/04）。
 */
@Slf4j
@Component
@RequiredArgsConstructor
@RocketMQMessageListener(topic = "generation-task-completed", consumerGroup = "billing-consumer")
public class GenerationResultListener implements RocketMQListener<String> {
    private final PointService pointService;
    private final ObjectMapper objectMapper;

    @Override
    public void onMessage(String message) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = objectMapper.readValue(message, Map.class);
            Long taskId = Long.parseLong(payload.get("taskId").toString());
            int actualCost = payload.get("actualCost") == null
                    ? ((Number) payload.get("estimatedCost")).intValue()
                    : ((Number) payload.get("actualCost")).intValue();
            pointService.settle(taskId, actualCost,
                    payload.get("modelType") == null ? "unknown" : payload.get("modelType").toString());
        } catch (Exception e) {
            log.error("consume completed message failed: {}", message, e);
        }
    }
}
