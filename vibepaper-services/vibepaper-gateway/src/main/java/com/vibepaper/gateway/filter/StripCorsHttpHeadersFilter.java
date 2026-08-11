package com.vibepaper.gateway.filter;

import org.springframework.cloud.gateway.filter.headers.HttpHeadersFilter;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

/**
 * Drop CORS headers coming from downstream (FastAPI / Spring apps) so the gateway
 * CorsWebFilter is the only source of Access-Control-Allow-Origin.
 */
@Component
public class StripCorsHttpHeadersFilter implements HttpHeadersFilter {

    @Override
    public HttpHeaders filter(HttpHeaders input, ServerWebExchange exchange) {
        HttpHeaders out = new HttpHeaders();
        input.forEach((key, values) -> {
            if (key != null && !key.regionMatches(true, 0, "Access-Control-", 0, "Access-Control-".length())) {
                out.put(key, values);
            }
        });
        return out;
    }

    @Override
    public boolean supports(Type type) {
        return type == Type.RESPONSE;
    }
}
