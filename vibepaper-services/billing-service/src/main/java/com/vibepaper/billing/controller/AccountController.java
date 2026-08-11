package com.vibepaper.billing.controller;

import com.vibepaper.billing.service.LedgerService;
import com.vibepaper.billing.service.PointService;
import com.vibepaper.common.context.RequestContext;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class AccountController {
    private final PointService pointService;
    private final LedgerService ledgerService;

    @GetMapping("/accounts/me")
    public Map<String, Object> me() {
        return pointService.getAccount(RequestContext.userIdLong());
    }

    @GetMapping("/accounts/me/usage")
    public List<Map<String, Object>> usage(
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to) {
        return ledgerService.usageStats(RequestContext.userIdLong(), from, to, "personal");
    }
}
