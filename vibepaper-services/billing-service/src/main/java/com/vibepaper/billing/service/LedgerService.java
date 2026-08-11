package com.vibepaper.billing.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.vibepaper.billing.entity.PointLedger;
import com.vibepaper.billing.mapper.PointLedgerMapper;
import com.vibepaper.common.api.PageResult;
import com.vibepaper.common.context.RequestContext;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * 点数流水查询（B-15）与用量统计（B-36）。
 */
@Service
@RequiredArgsConstructor
public class LedgerService {
    private final PointLedgerMapper ledgerMapper;

    public PageResult<PointLedger> page(int page, int pageSize, String type, OffsetDateTime from, OffsetDateTime to) {
        Long userId = RequestContext.userIdLong();
        Page<PointLedger> p = ledgerMapper.selectPage(new Page<>(page, pageSize),
                new LambdaQueryWrapper<PointLedger>()
                        .eq(PointLedger::getUserId, userId)
                        .eq(type != null && !type.isBlank(), PointLedger::getLedgerType, type)
                        .ge(from != null, PointLedger::getCreatedAt, from)
                        .le(to != null, PointLedger::getCreatedAt, to)
                        .orderByDesc(PointLedger::getCreatedAt));
        return PageResult.of(p.getRecords(), p.getTotal(), page, pageSize);
    }

    public List<PointLedger> export(OffsetDateTime from, OffsetDateTime to) {
        Long userId = RequestContext.userIdLong();
        return ledgerMapper.selectList(new LambdaQueryWrapper<PointLedger>()
                .eq(PointLedger::getUserId, userId)
                .ge(from != null, PointLedger::getCreatedAt, from)
                .le(to != null, PointLedger::getCreatedAt, to)
                .orderByDesc(PointLedger::getCreatedAt));
    }

    public List<Map<String, Object>> usageStats(Long userId, OffsetDateTime from, OffsetDateTime to, String scope) {
        List<PointLedger> ledgers = ledgerMapper.selectList(new LambdaQueryWrapper<PointLedger>()
                .eq(PointLedger::getUserId, userId)
                .in(PointLedger::getLedgerType, List.of("settle", "freeze"))
                .ge(from != null, PointLedger::getCreatedAt, from)
                .le(to != null, PointLedger::getCreatedAt, to));
        return ledgers.stream().map(l -> Map.<String, Object>of(
                "date", l.getCreatedAt().toLocalDate().toString(),
                "points", l.getPoints(),
                "type", l.getLedgerType(),
                "reference", l.getReference() == null ? "" : l.getReference())).toList();
    }
}
