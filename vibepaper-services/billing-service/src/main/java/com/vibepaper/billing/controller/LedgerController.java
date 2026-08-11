package com.vibepaper.billing.controller;

import com.vibepaper.billing.entity.PointLedger;
import com.vibepaper.billing.service.LedgerService;
import com.vibepaper.common.api.PageResult;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.List;

@RestController
@RequestMapping("/api/v1/ledgers")
@RequiredArgsConstructor
public class LedgerController {
    private final LedgerService ledgerService;

    @GetMapping
    public PageResult<PointLedger> page(@RequestParam(defaultValue = "1") int page,
                                        @RequestParam(defaultValue = "20") int pageSize,
                                        @RequestParam(required = false) String type,
                                        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
                                        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to) {
        return ledgerService.page(page, pageSize, type, from, to);
    }

    @GetMapping("/export")
    public ResponseEntity<byte[]> export(
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to) {
        List<PointLedger> ledgers = ledgerService.export(from, to);
        StringBuilder csv = new StringBuilder("ledger_id,user_id,ledger_type,direction,points,balance_after,task_id,reference,created_at\n");
        for (PointLedger l : ledgers) {
            csv.append(l.getId()).append(',').append(l.getUserId()).append(',').append(l.getLedgerType()).append(',')
                    .append(l.getDirection()).append(',').append(l.getPoints()).append(',').append(l.getBalanceAfter())
                    .append(',').append(l.getTaskId()).append(',').append(sanitize(l.getReference())).append(',')
                    .append(l.getCreatedAt()).append('\n');
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=ledgers.csv")
                .contentType(MediaType.parseMediaType("text/csv; charset=UTF-8"))
                .body(csv.toString().getBytes(StandardCharsets.UTF_8));
    }

    private String sanitize(String s) {
        if (s == null) {
            return "";
        }
        return s.replace(",", " ").replace("\n", " ");
    }
}
