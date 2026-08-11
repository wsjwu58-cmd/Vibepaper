package com.vibepaper.enterprise.controller;

import com.vibepaper.enterprise.entity.AllocationRecord;
import com.vibepaper.enterprise.entity.EnterpriseInvitation;
import com.vibepaper.enterprise.service.EnterpriseService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class EnterpriseController {
    private final EnterpriseService enterpriseService;

    @PostMapping("/api/v1/enterprises")
    public Map<String, Object> create(@RequestBody Map<String, String> body) {
        return enterpriseService.create(body.getOrDefault("name", "我的企业"));
    }

    @GetMapping("/api/v1/enterprises/me")
    public Map<String, Object> me() {
        return enterpriseService.myEnterprise();
    }

    @PostMapping("/api/v1/enterprises/{id}/invitations")
    public EnterpriseInvitation createInvitation(@PathVariable Long id) {
        return enterpriseService.createInvitation(id);
    }

    @PostMapping("/api/v1/invitations/{token}/accept")
    public Map<String, String> accept(@PathVariable String token) {
        enterpriseService.acceptInvitation(token);
        return Map.of("status", "ok");
    }

    @GetMapping("/api/v1/enterprises/{id}/members")
    public List<Map<String, Object>> members(@PathVariable Long id) {
        return enterpriseService.members(id);
    }

    @PostMapping("/api/v1/enterprises/{id}/members/{memberId}/allocate")
    public Map<String, String> allocate(@PathVariable Long id, @PathVariable Long memberId,
                                        @RequestBody Map<String, Object> body) {
        enterpriseService.allocate(id, memberId, ((Number) body.get("amount")).intValue());
        return Map.of("status", "ok");
    }

    @PostMapping("/api/v1/enterprises/{id}/members/{memberId}/recycle")
    public Map<String, String> recycle(@PathVariable Long id, @PathVariable Long memberId,
                                       @RequestBody Map<String, Object> body) {
        enterpriseService.recycle(id, memberId, ((Number) body.get("amount")).intValue());
        return Map.of("status", "ok");
    }

    @DeleteMapping("/api/v1/enterprises/{id}/members/{memberId}")
    public Map<String, String> remove(@PathVariable Long id, @PathVariable Long memberId) {
        enterpriseService.removeMember(id, memberId);
        return Map.of("status", "ok");
    }

    @GetMapping("/api/v1/enterprises/{id}/allocation-records")
    public List<AllocationRecord> records(@PathVariable Long id,
                                          @RequestParam(required = false) String search,
                                          @RequestParam(defaultValue = "1") int page,
                                          @RequestParam(defaultValue = "50") int pageSize) {
        return enterpriseService.allocationRecords(id, search, page, pageSize);
    }

    @GetMapping("/api/v1/enterprises/{id}/allocation-records/export")
    public ResponseEntity<byte[]> exportRecords(@PathVariable Long id) {
        List<AllocationRecord> records = enterpriseService.allocationRecords(id, null, 1, 5000);
        StringBuilder csv = new StringBuilder("id,enterprise_id,operator_id,member_id,alloc_type,points,balance_after,created_at\n");
        for (AllocationRecord r : records) {
            csv.append(r.getId()).append(',').append(r.getEnterpriseId()).append(',').append(r.getOperatorId())
                    .append(',').append(r.getMemberId()).append(',').append(r.getAllocType()).append(',')
                    .append(r.getPoints()).append(',').append(r.getBalanceAfter()).append(',')
                    .append(r.getCreatedAt()).append('\n');
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=allocation-records.csv")
                .contentType(MediaType.parseMediaType("text/csv; charset=UTF-8"))
                .body(csv.toString().getBytes(StandardCharsets.UTF_8));
    }

    @GetMapping("/api/v1/enterprises/{id}/usage")
    public List<Map<String, Object>> usage(@PathVariable Long id,
                                           @RequestParam(defaultValue = "enterprise") String scope,
                                           @RequestParam(required = false) OffsetDateTime from,
                                           @RequestParam(required = false) OffsetDateTime to) {
        return enterpriseService.usage(id, scope, from, to);
    }

    @GetMapping("/api/v1/enterprises/{id}/assets")
    public List<Map<String, Object>> assets(@PathVariable Long id) {
        return enterpriseService.assets(id);
    }

    @PutMapping("/api/v1/enterprises/{id}")
    public Map<String, Object> rename(@PathVariable Long id, @RequestBody Map<String, String> body) {
        return enterpriseService.updateName(id, body.get("name"));
    }

    @DeleteMapping("/api/v1/enterprises/{id}")
    public Map<String, String> dissolve(@PathVariable Long id) {
        enterpriseService.dissolve(id);
        return Map.of("status", "ok");
    }
}
