package com.vibepaper.billing.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.billing.entity.PointLedger;
import com.vibepaper.billing.entity.RechargeOrder;
import com.vibepaper.billing.entity.RechargePackage;
import com.vibepaper.billing.mapper.PointLedgerMapper;
import com.vibepaper.billing.mapper.RechargeOrderMapper;
import com.vibepaper.billing.mapper.RechargePackageMapper;
import com.vibepaper.billing.service.LedgerService;
import com.vibepaper.billing.service.PointService;
import com.vibepaper.common.id.SnowflakeIdGenerator;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * 内部接口：identity 初始化账户、enterprise 分配/回收、admin 交易查询。
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalController {
    private final PointService pointService;
    private final LedgerService ledgerService;
    private final RechargeOrderMapper orderMapper;
    private final PointLedgerMapper ledgerMapper;
    private final RechargePackageMapper packageMapper;
    private final SnowflakeIdGenerator idGenerator;

    @PostMapping("/accounts")
    public Map<String, Object> createAccount(@RequestBody Map<String, Object> body) {
        Long userId = ((Number) body.get("userId")).longValue();
        int initial = body.get("initialPoints") == null ? 0 : ((Number) body.get("initialPoints")).intValue();
        return Map.of("status", "ok",
                "account", pointService.createAccountInternal(userId, "user", initial));
    }

    @GetMapping("/accounts/{userId}")
    public Map<String, Object> getAccount(@PathVariable Long userId) {
        return pointService.getAccount(userId);
    }

    @PostMapping("/accounts/{userId}/credit")
    public Map<String, Object> credit(@PathVariable Long userId, @RequestBody Map<String, Object> body) {
        int points = ((Number) body.get("points")).intValue();
        String reason = body.get("reason") == null ? "credit" : body.get("reason").toString();
        pointService.credit(userId, points, reason);
        return pointService.getAccount(userId);
    }

    @PutMapping("/accounts/{userId}/enterprise")
    public Map<String, Object> linkEnterprise(@PathVariable Long userId, @RequestBody Map<String, Object> body) {
        Long enterpriseId = ((Number) body.get("enterpriseId")).longValue();
        pointService.createAccountInternal(userId, "user", 0, enterpriseId);
        return pointService.getAccount(userId);
    }

    @PostMapping("/allocate")
    public Map<String, String> allocate(@RequestBody Map<String, Object> body) {
        pointService.allocate(((Number) body.get("enterpriseId")).longValue(),
                ((Number) body.get("memberId")).longValue(),
                ((Number) body.get("amount")).intValue());
        return Map.of("status", "ok");
    }

    @PostMapping("/recycle")
    public Map<String, String> recycle(@RequestBody Map<String, Object> body) {
        pointService.recycle(((Number) body.get("enterpriseId")).longValue(),
                ((Number) body.get("memberId")).longValue(),
                ((Number) body.get("amount")).intValue());
        return Map.of("status", "ok");
    }

    @PostMapping("/tasks/{taskId}/settle")
    public Map<String, String> settle(@PathVariable Long taskId, @RequestBody Map<String, Object> body) {
        int actualCost = body.get("actualCost") == null
                ? 0 : ((Number) body.get("actualCost")).intValue();
        pointService.settle(taskId, actualCost,
                body.get("modelType") == null ? "unknown" : body.get("modelType").toString());
        return Map.of("status", "settled");
    }

    @PostMapping("/tasks/{taskId}/fail")
    public Map<String, String> fail(@PathVariable Long taskId, @RequestBody Map<String, Object> body) {
        pointService.unfreezeFail(taskId,
                body.get("errorCode") == null ? "MODEL_UNAVAILABLE" : body.get("errorCode").toString());
        return Map.of("status", "refunded");
    }

    @GetMapping("/accounts/{userId}/ledgers")
    public List<PointLedger> ledgers(@PathVariable Long userId,
                                     @RequestParam(required = false) OffsetDateTime from,
                                     @RequestParam(required = false) OffsetDateTime to) {
        return ledgerMapper.selectList(new LambdaQueryWrapper<PointLedger>()
                .eq(PointLedger::getUserId, userId)
                .ge(from != null, PointLedger::getCreatedAt, from)
                .le(to != null, PointLedger::getCreatedAt, to)
                .orderByDesc(PointLedger::getCreatedAt).last("limit 500"));
    }

    @GetMapping("/enterprises/{enterpriseId}/usage")
    public List<Map<String, Object>> enterpriseUsage(@PathVariable Long enterpriseId,
                                                     @RequestParam(required = false) OffsetDateTime from,
                                                     @RequestParam(required = false) OffsetDateTime to) {
        return ledgerService.usageStats(-enterpriseId, from, to, "enterprise");
    }

    @GetMapping("/transactions")
    public List<RechargeOrder> transactions(@RequestParam(required = false) String status) {
        return orderMapper.selectList(new LambdaQueryWrapper<RechargeOrder>()
                .eq(status != null && !status.isBlank(), RechargeOrder::getStatus, status)
                .orderByDesc(RechargeOrder::getCreatedAt).last("limit 500"));
    }

    @PostMapping("/packages")
    public RechargePackage createPackage(@RequestBody Map<String, Object> body) {
        RechargePackage pkg = new RechargePackage();
        pkg.setId(idGenerator.nextId());
        pkg.setName(body.get("name").toString());
        pkg.setPoints(((Number) body.get("points")).intValue());
        pkg.setPriceCny(((Number) body.get("priceCny")).intValue());
        pkg.setValidityDays(body.get("validityDays") == null ? null : ((Number) body.get("validityDays")).intValue());
        pkg.setEnabled(body.get("enabled") == null || (Boolean) body.get("enabled"));
        pkg.setPriority(body.get("priority") == null ? 0 : ((Number) body.get("priority")).intValue());
        pkg.setCreatedAt(java.time.OffsetDateTime.now());
        packageMapper.insert(pkg);
        return pkg;
    }

    @PutMapping("/packages/{packageId}")
    public RechargePackage updatePackage(@PathVariable Long packageId, @RequestBody Map<String, Object> body) {
        RechargePackage pkg = packageMapper.selectById(packageId);
        if (pkg == null) {
            throw com.vibepaper.common.api.ApiException.notFound("套餐不存在");
        }
        if (body.get("name") != null) {
            pkg.setName(body.get("name").toString());
        }
        if (body.get("points") != null) {
            pkg.setPoints(((Number) body.get("points")).intValue());
        }
        if (body.get("priceCny") != null) {
            pkg.setPriceCny(((Number) body.get("priceCny")).intValue());
        }
        if (body.get("enabled") != null) {
            pkg.setEnabled((Boolean) body.get("enabled"));
        }
        if (body.get("priority") != null) {
            pkg.setPriority(((Number) body.get("priority")).intValue());
        }
        packageMapper.updateById(pkg);
        return pkg;
    }

    @DeleteMapping("/packages/{packageId}")
    public Map<String, String> deletePackage(@PathVariable Long packageId) {
        packageMapper.deleteById(packageId);
        return Map.of("status", "ok");
    }
}
