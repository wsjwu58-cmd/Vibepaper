package com.vibepaper.billing.controller;

import com.vibepaper.billing.entity.RechargeOrder;
import com.vibepaper.billing.entity.RechargePackage;
import com.vibepaper.billing.entity.SubscriptionPlan;
import com.vibepaper.billing.entity.UserSubscription;
import com.vibepaper.billing.service.RechargeService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class RechargeController {
    private final RechargeService rechargeService;

    @GetMapping("/api/v1/packages")
    public List<RechargePackage> packages() {
        return rechargeService.packages();
    }

    @GetMapping("/api/v1/subscriptions/plans")
    public List<SubscriptionPlan> plans() {
        return rechargeService.plans();
    }

    @GetMapping("/api/v1/subscriptions/me")
    public UserSubscription mySubscription() {
        return rechargeService.mySubscription();
    }

    @PostMapping("/api/v1/subscriptions")
    public UserSubscription subscribe(@RequestBody Map<String, Object> body) {
        return rechargeService.subscribe(((Number) body.get("planId")).longValue());
    }

    @PostMapping("/api/v1/recharge/orders")
    public RechargeOrder createOrder(@RequestHeader("Idempotency-Key") String idempotencyKey,
                                     @RequestBody Map<String, Object> body) {
        Long packageId = body.get("packageId") == null ? null : ((Number) body.get("packageId")).longValue();
        Integer points = body.get("points") == null ? null : ((Number) body.get("points")).intValue();
        return rechargeService.createOrder(packageId, points, idempotencyKey);
    }

    @PostMapping("/api/v1/recharge/orders/{orderId}/mock-pay")
    public RechargeOrder mockPay(@PathVariable Long orderId) {
        return rechargeService.mockPay(orderId);
    }

    @PostMapping("/api/v1/recharge/orders/{orderId}/callback")
    public RechargeOrder callback(@PathVariable Long orderId, @RequestBody Map<String, String> body) {
        return rechargeService.callback(orderId, body.getOrDefault("status", "success"));
    }
}
