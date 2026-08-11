package com.vibepaper.enterprise.controller;

import com.vibepaper.enterprise.service.EnterpriseService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalController {
    private final EnterpriseService enterpriseService;

    @GetMapping("/enterprises/{enterpriseId}/settings")
    public Map<String, Object> settings(@PathVariable Long enterpriseId) {
        return enterpriseService.settings(enterpriseId);
    }
}
