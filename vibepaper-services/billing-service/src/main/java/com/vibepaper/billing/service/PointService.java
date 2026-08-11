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
import java.util.HashMap;
import java.util.Map;

/**
 * 点数核心服务（PRD §5.3 / BILL-01~07）。
 * 冻结不扣 balance、只增加 frozen_points；结算时扣 balance 并解冻预扣；
 * 失败/超时/取消全额解冻；流水只追加；UNIQUE(task_id, ledger_type)。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PointService {
    private final PointAccountMapper accountMapper;
    private final PointLedgerMapper ledgerMapper;
    private final PointReservationMapper reservationMapper;
    private final OutboxEventMapper outboxMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final com.vibepaper.billing.feign.EnterpriseClient enterpriseClient;

    public Map<String, Object> getAccount(Long userId) {
        PointAccount account = accountMapper.selectById(userId);
        if (account == null) {
            account = createAccountInternal(userId, "user", 0);
        }
        return Map.of("balance", account.getBalance(), "frozenPoints", account.getFrozenPoints(),
                "availablePoints", account.available());
    }

    @Transactional
    public PointAccount createAccountInternal(Long userId, String ownerType, int initialPoints) {
        return createAccountInternal(userId, ownerType, initialPoints, null);
    }

    @Transactional
    public PointAccount createAccountInternal(Long userId, String ownerType, int initialPoints, Long enterpriseId) {
        PointAccount existing = accountMapper.selectById(userId);
        if (existing != null) {
            if (enterpriseId != null && existing.getEnterpriseId() == null) {
                existing.setEnterpriseId(enterpriseId);
                accountMapper.updateById(existing);
            }
            return existing;
        }
        PointAccount account = new PointAccount();
        account.setUserId(userId);
        account.setOwnerType(ownerType);
        account.setEnterpriseId(enterpriseId);
        account.setBalance(initialPoints);
        account.setFrozenPoints(0);
        account.setStatus("active");
        account.setUpdatedAt(OffsetDateTime.now());
        accountMapper.insert(account);
        return account;
    }

    /**
     * BILL-01：提交任务冻结（含 BILL-07 企业共享池）。
     */
    @Transactional
    public Map<String, Object> freeze(FreezeRequest req) {
        Long userId = RequestContext.userIdLong();
        if (req.estimatedCost() < 1) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "estimated_cost 必须 ≥ 1");
        }
        PointAccount account = accountMapper.selectByUserIdForUpdate(userId);
        if (account == null) {
            account = createAccountInternal(userId, "user", 0);
            account = accountMapper.selectByUserIdForUpdate(userId);
        }
        PointAccount target = account;
        if (account.available() < req.estimatedCost() && account.getEnterpriseId() != null
                && isSharedPoolEnabled(account.getEnterpriseId())) {
            PointAccount ent = accountMapper.selectByUserIdForUpdate(-account.getEnterpriseId());
            if (ent != null && ent.available() >= req.estimatedCost()) {
                target = ent;
            }
        }
        if (target.available() < req.estimatedCost()) {
            throw new ApiException(ErrorCode.INSUFFICIENT_POINTS,
                    "可用点数不足，当前可用 " + target.available() + "，需要 " + req.estimatedCost(),
                    Map.of("available", target.available(), "required", req.estimatedCost()), false,
                    org.springframework.http.HttpStatus.PAYMENT_REQUIRED);
        }

        Long taskId = idGenerator.nextId();
        target.setFrozenPoints(target.getFrozenPoints() + req.estimatedCost());
        target.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(target);

        PointReservation reservation = new PointReservation();
        reservation.setId(idGenerator.nextId());
        reservation.setUserId(userId);
        reservation.setAccountOwnerId(target.getUserId());
        reservation.setTaskId(taskId);
        reservation.setEstimatedCost(req.estimatedCost());
        reservation.setStatus("pending");
        reservation.setFreezeDeadline(OffsetDateTime.now().plusMinutes(5));
        reservation.setCreatedAt(OffsetDateTime.now());
        reservationMapper.insert(reservation);

        ledger(target.getUserId(), "freeze", "out", req.estimatedCost(), taskId, null,
                "task_freeze:" + req.modelType());

        String payload = writeJson(Map.of(
                "taskId", taskId.toString(),
                "userId", req.userId() == null ? RequestContext.userIdLong().toString() : req.userId().toString(),
                "nodeId", req.nodeId() == null ? "" : req.nodeId().toString(),
                "canvasId", req.canvasId() == null ? "" : req.canvasId().toString(),
                "modelType", req.modelType(),
                "modelParams", req.modelParams() == null ? Map.of() : req.modelParams(),
                "estimatedCost", req.estimatedCost(),
                "source", req.source() == null ? "user" : req.source(),
                "idempotencyKey", req.idempotencyKey() == null ? "" : req.idempotencyKey()));
        outbox("generation-task-created", payload, req.idempotencyKey());
        log.info("points frozen user_id={} task_id={} cost={}", userId, taskId, req.estimatedCost());
        return Map.of("taskId", taskId.toString(), "status", "queued",
                "estimatedCost", req.estimatedCost(), "frozenPoints", target.getFrozenPoints());
    }

    /**
     * BILL-03：成功结算（MQ 回调）。actual_cost 默认 = estimated_cost。
     */
    @Transactional
    public void settle(Long taskId, int actualCost, String modelType) {
        PointReservation reservation = reservationMapper.selectOne(
                new LambdaQueryWrapper<PointReservation>().eq(PointReservation::getTaskId, taskId));
        if (reservation == null || !"pending".equals(reservation.getStatus())) {
            log.warn("settle skipped for task {} status={}", taskId, reservation == null ? "null" : reservation.getStatus());
            return;
        }
        if (actualCost < 0 || actualCost > reservation.getEstimatedCost() + reservation.getEstimatedCost()) {
            throw new ApiException(ErrorCode.BILLING_ERROR, "结算金额异常: " + actualCost, null, false,
                    org.springframework.http.HttpStatus.CONFLICT);
        }
        Long accountOwner = reservation.getAccountOwnerId() == null ? reservation.getUserId() : reservation.getAccountOwnerId();
        PointAccount account = accountMapper.selectByUserIdForUpdate(accountOwner);
        if (account.getBalance() < actualCost) {
            reservation.setStatus("settlement_error");
            reservationMapper.updateById(reservation);
            throw new ApiException(ErrorCode.BILLING_ERROR, "计费异常，已通知客服", null, false,
                    org.springframework.http.HttpStatus.CONFLICT);
        }
        account.setBalance(account.getBalance() - actualCost);
        account.setFrozenPoints(account.getFrozenPoints() - reservation.getEstimatedCost());
        account.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(account);

        ledger(accountOwner, "settle", "out", actualCost, taskId, null, "task_settle:" + modelType);
        ledger(accountOwner, "unfreeze_settle", "in", reservation.getEstimatedCost(), taskId, null, "task_settle");

        reservation.setStatus("settled");
        reservation.setSettledAt(OffsetDateTime.now());
        reservationMapper.updateById(reservation);
        log.info("points settled user_id={} task_id={} actual={}", reservation.getUserId(), taskId, actualCost);
    }

    /**
     * BILL-04：失败全额解冻。
     */
    @Transactional
    public void unfreezeFail(Long taskId, String errorCode) {
        PointReservation reservation = pendingReservation(taskId);
        unfreeze(reservation, "unfreeze_fail", "task_fail:" + errorCode);
    }

    /**
     * BILL-05：用户取消（queued）全额解冻。
     */
    @Transactional
    public void cancel(Long taskId) {
        PointReservation reservation = pendingReservation(taskId);
        unfreeze(reservation, "unfreeze_cancel", "task_cancel");
        String payload = writeJson(Map.of("taskId", taskId.toString()));
        outbox("generation-task-cancelled", payload, "cancel-" + taskId);
    }

    /**
     * BILL-02：排队超时解冻（调度任务调用）。
     */
    @Transactional
    public void unfreezeTimeout(Long taskId) {
        PointReservation reservation = pendingReservation(taskId);
        unfreeze(reservation, "unfreeze_timeout", "task_timeout");
        String payload = writeJson(Map.of("taskId", taskId.toString()));
        outbox("generation-task-expired", payload, "expire-" + taskId);
    }

    /**
     * §5.4：企业分配点数（enterprise 扣减 allocatable → 成员增加 available）。
     */
    @Transactional
    public void allocate(Long enterpriseId, Long memberId, int amount) {
        if (amount < 1) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "分配点数必须 ≥ 1");
        }
        Long entKey = -enterpriseId;
        PointAccount ent = accountMapper.selectByUserIdForUpdate(entKey);
        if (ent == null) {
            throw ApiException.badRequest(ErrorCode.INSUFFICIENT_POINTS, "企业账户未开通");
        }
        if (ent.available() < amount) {
            throw ApiException.badRequest(ErrorCode.INSUFFICIENT_POINTS, "可分配点数不足，当前可分配 " + ent.available());
        }
        PointAccount member = accountMapper.selectByUserIdForUpdate(memberId);
        if (member == null) {
            member = createAccountInternal(memberId, "user", 0);
            member = accountMapper.selectByUserIdForUpdate(memberId);
        }
        ent.setBalance(ent.getBalance() - amount);
        ent.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(ent);
        member.setBalance(member.getBalance() + amount);
        if (member.getEnterpriseId() == null) {
            member.setEnterpriseId(enterpriseId);
        }
        member.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(member);
        ledger(memberId, "allocate", "in", amount, null, null, "enterprise_allocate:" + enterpriseId);
        log.info("points allocated ent={} member={} amount={}", enterpriseId, memberId, amount);
    }

    /**
     * §5.4 / §9.2：回收点数（仅 available，不触及 frozen）。
     */
    @Transactional
    public void recycle(Long enterpriseId, Long memberId, int amount) {
        if (amount < 1) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "回收点数必须 ≥ 1");
        }
        PointAccount member = accountMapper.selectByUserIdForUpdate(memberId);
        if (member == null || member.available() < amount) {
            throw ApiException.badRequest(ErrorCode.INSUFFICIENT_POINTS,
                    "最多可回收 " + (member == null ? 0 : member.available()) + " 点");
        }
        Long entKey = -enterpriseId;
        PointAccount ent = accountMapper.selectByUserIdForUpdate(entKey);
        if (ent == null) {
            ent = createAccountInternal(entKey, "enterprise", 0);
            ent = accountMapper.selectByUserIdForUpdate(entKey);
        }
        member.setBalance(member.getBalance() - amount);
        member.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(member);
        ent.setBalance(ent.getBalance() + amount);
        ent.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(ent);
        ledger(memberId, "recycle", "out", amount, null, null, "enterprise_recycle:" + enterpriseId);
        log.info("points recycled ent={} member={} amount={}", enterpriseId, memberId, amount);
    }

    @Transactional
    public void credit(Long userId, int points, String reason) {
        if (points <= 0) {
            throw ApiException.badRequest(ErrorCode.INVALID_INPUT, "入账点数必须 > 0");
        }
        PointAccount account = accountMapper.selectByUserIdForUpdate(userId);
        if (account == null) {
            account = createAccountInternal(userId, "user", 0);
            account = accountMapper.selectByUserIdForUpdate(userId);
        }
        account.setBalance(account.getBalance() + points);
        account.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(account);
        ledger(userId, "recharge", "in", points, null, null, reason);
    }

    private void unfreeze(PointReservation reservation, String ledgerType, String reference) {
        Long accountOwner = reservation.getAccountOwnerId() == null ? reservation.getUserId() : reservation.getAccountOwnerId();
        PointAccount account = accountMapper.selectByUserIdForUpdate(accountOwner);
        if (account.getFrozenPoints() < reservation.getEstimatedCost()) {
            log.error("frozen points inconsistent user={} frozen={} reserve={}",
                    reservation.getUserId(), account.getFrozenPoints(), reservation.getEstimatedCost());
            throw new ApiException(ErrorCode.BILLING_ERROR, "冻结点数不一致，需人工处理", null, false,
                    org.springframework.http.HttpStatus.CONFLICT);
        }
        account.setFrozenPoints(account.getFrozenPoints() - reservation.getEstimatedCost());
        account.setUpdatedAt(OffsetDateTime.now());
        accountMapper.updateById(account);
        ledger(accountOwner, ledgerType, "in", reservation.getEstimatedCost(),
                reservation.getTaskId(), null, reference);
        reservation.setStatus(switch (ledgerType) {
            case "unfreeze_timeout" -> "expired";
            case "unfreeze_cancel" -> "cancelled";
            default -> "refunded";
        });
        reservation.setSettledAt(OffsetDateTime.now());
        reservationMapper.updateById(reservation);
    }

    private PointReservation pendingReservation(Long taskId) {
        PointReservation reservation = reservationMapper.selectOne(
                new LambdaQueryWrapper<PointReservation>().eq(PointReservation::getTaskId, taskId));
        if (reservation == null || !"pending".equals(reservation.getStatus())) {
            throw new ApiException(ErrorCode.TASK_STATE_INVALID,
                    "任务状态不允许该操作: " + (reservation == null ? "不存在" : reservation.getStatus()));
        }
        return reservation;
    }

    private void ledger(Long userId, String type, String direction, int points, Long taskId, Long orderId, String reference) {
        PointLedger ledger = new PointLedger();
        ledger.setId(idGenerator.nextId());
        ledger.setUserId(userId);
        ledger.setLedgerType(type);
        ledger.setDirection(direction);
        ledger.setPoints(points);
        PointAccount account = accountMapper.selectById(userId);
        ledger.setBalanceAfter(account == null ? 0 : account.available());
        ledger.setTaskId(taskId);
        ledger.setOrderId(orderId);
        ledger.setReference(reference);
        ledger.setCreatedAt(OffsetDateTime.now());
        ledgerMapper.insert(ledger);
    }

    private void outbox(String eventType, String payload, String idempotencyKey) {
        OutboxEvent event = new OutboxEvent();
        event.setId(idGenerator.nextId());
        event.setEventType(eventType);
        event.setPayload(payload);
        event.setStatus("pending");
        event.setIdempotencyKey(idempotencyKey);
        event.setCreatedAt(OffsetDateTime.now());
        outboxMapper.insert(event);
    }

    private boolean isSharedPoolEnabled(Long enterpriseId) {
        try {
            Map<String, Object> settings = enterpriseClient.getSettings(enterpriseId);
            return Boolean.TRUE.equals(settings.get("sharedPoolEnabled"));
        } catch (Exception e) {
            return false;
        }
    }

    private String writeJson(Object obj) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public record FreezeRequest(Long userId, Long nodeId, Long canvasId, String modelType,
                                Map<String, Object> modelParams, int estimatedCost, String source,
                                String idempotencyKey) {
    }
}
