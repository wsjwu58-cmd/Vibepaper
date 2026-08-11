package com.vibepaper.billing.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.billing.entity.*;
import com.vibepaper.billing.mapper.*;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.api.ErrorCode;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 充值/订阅（P0｜F-19/B-20）。真实支付回调合规后启用，开发期使用 mock 回调。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RechargeService {
    private final RechargeOrderMapper orderMapper;
    private final RechargePackageMapper packageMapper;
    private final SubscriptionPlanMapper planMapper;
    private final UserSubscriptionMapper subscriptionMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final PointService pointService;

    public List<RechargePackage> packages() {
        return packageMapper.selectList(new LambdaQueryWrapper<RechargePackage>()
                .eq(RechargePackage::getEnabled, true).orderByAsc(RechargePackage::getPriority));
    }

    public List<SubscriptionPlan> plans() {
        return planMapper.selectList(new LambdaQueryWrapper<SubscriptionPlan>()
                .eq(SubscriptionPlan::getEnabled, true));
    }

    @Transactional
    public RechargeOrder createOrder(Long packageId, Integer points, String idempotencyKey) {
        Long userId = RequestContext.userIdLong();
        RechargeOrder existing = orderMapper.selectOne(new LambdaQueryWrapper<RechargeOrder>()
                .eq(RechargeOrder::getIdempotencyKey, idempotencyKey));
        if (existing != null) {
            return existing;
        }
        RechargeOrder order = new RechargeOrder();
        order.setId(idGenerator.nextId());
        order.setUserId(userId);
        order.setOrderNo("VP" + System.currentTimeMillis() + UUID.randomUUID().toString().substring(0, 6));
        order.setChannel("mock");
        order.setStatus("pending");
        order.setIdempotencyKey(idempotencyKey);
        order.setCreatedAt(OffsetDateTime.now());
        if (packageId != null) {
            RechargePackage pkg = packageMapper.selectById(packageId);
            if (pkg == null || !Boolean.TRUE.equals(pkg.getEnabled())) {
                throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "套餐不存在或已下架");
            }
            order.setPackageId(pkg.getId());
            order.setPoints(pkg.getPoints());
            order.setAmountCny(pkg.getPriceCny());
        } else {
            if (points == null || points < 100 || points % 100 != 0) {
                throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "自定义点数须为 100 的整数倍");
            }
            order.setPoints(points);
            order.setAmountCny(points / 100);
        }
        orderMapper.insert(order);
        return order;
    }

    @Transactional
    public RechargeOrder mockPay(Long orderId) {
        return markPaid(orderId, "success");
    }

    @Transactional
    public RechargeOrder callback(Long orderId, String status) {
        return markPaid(orderId, status);
    }

    private RechargeOrder markPaid(Long orderId, String status) {
        RechargeOrder order = orderMapper.selectById(orderId);
        if (order == null) {
            throw ApiException.notFound("订单不存在");
        }
        if (!"pending".equals(order.getStatus())) {
            return order; // 幂等：已处理直接返回
        }
        if ("success".equals(status)) {
            order.setStatus("success");
            order.setPaidAt(OffsetDateTime.now());
            orderMapper.updateById(order);
            pointService.credit(order.getUserId(), order.getPoints(), "recharge_order:" + order.getOrderNo());
            log.info("recharge success user_id={} order={} points={}", order.getUserId(), order.getOrderNo(), order.getPoints());
        } else {
            order.setStatus("failed");
            orderMapper.updateById(order);
        }
        return order;
    }

    @Transactional
    public UserSubscription subscribe(Long planId) {
        Long userId = RequestContext.userIdLong();
        SubscriptionPlan plan = planMapper.selectById(planId);
        if (plan == null || !Boolean.TRUE.equals(plan.getEnabled())) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "订阅方案不存在或已下架");
        }
        UserSubscription sub = new UserSubscription();
        sub.setId(idGenerator.nextId());
        sub.setUserId(userId);
        sub.setPlanId(planId);
        sub.setStatus("active");
        sub.setStartedAt(OffsetDateTime.now());
        sub.setExpiresAt(OffsetDateTime.now().plusMonths(1));
        subscriptionMapper.insert(sub);
        return sub;
    }

    public UserSubscription mySubscription() {
        Long userId = RequestContext.userIdLong();
        return subscriptionMapper.selectOne(new LambdaQueryWrapper<UserSubscription>()
                .eq(UserSubscription::getUserId, userId).eq(UserSubscription::getStatus, "active")
                .orderByDesc(UserSubscription::getStartedAt).last("limit 1"));
    }
}
