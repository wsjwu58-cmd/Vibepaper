package com.vibepaper.common.context;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * 解析网关透传身份头，并写入 MDC（request_id）。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class UserContextFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String requestId = request.getHeader(RequestContext.HEADER_REQUEST_ID);
        if (requestId == null || requestId.isBlank()) {
            requestId = UUID.randomUUID().toString().replace("-", "");
        }
        RequestContext.set(
                request.getHeader(RequestContext.HEADER_USER_ID),
                request.getHeader(RequestContext.HEADER_USER_ROLE),
                request.getHeader(RequestContext.HEADER_ENTERPRISE_ID),
                requestId);
        MDC.put("request_id", requestId);
        response.setHeader(RequestContext.HEADER_REQUEST_ID, requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("request_id");
            RequestContext.clear();
        }
    }
}
