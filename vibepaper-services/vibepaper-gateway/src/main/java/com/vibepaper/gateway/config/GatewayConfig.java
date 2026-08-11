package com.vibepaper.gateway.config;

import com.vibepaper.common.security.JwtUtil;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class GatewayConfig {

    @Bean
    public JwtUtil jwtUtil(@Value("${vibepaper.jwt.secret}") String secret,
                           @Value("${vibepaper.jwt.access-ttl:900}") long accessTtl,
                           @Value("${vibepaper.jwt.refresh-ttl:604800}") long refreshTtl) {
        return new JwtUtil(secret, accessTtl, refreshTtl);
    }

    @Bean
    public CorsWebFilter corsWebFilter() {
        CorsConfiguration config = new CorsConfiguration();
        // Frontend uses Bearer tokens (not cookies); avoid reflecting Origin + "*" duplicates
        config.addAllowedOriginPattern("http://localhost:*");
        config.addAllowedOriginPattern("http://127.0.0.1:*");
        config.addAllowedHeader("*");
        config.addAllowedMethod("*");
        config.setExposedHeaders(java.util.List.of(HttpHeaders.AUTHORIZATION, "Idempotency-Key"));
        config.setMaxAge(3600L);
        config.setAllowCredentials(false);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return new CorsWebFilter(source);
    }
}
