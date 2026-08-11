package com.vibepaper.identity.config;

import com.vibepaper.common.security.JwtUtil;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JwtConfig {

    @Bean
    public JwtUtil jwtUtil(@Value("${vibepaper.jwt.secret}") String secret,
                           @Value("${vibepaper.jwt.access-ttl:900}") long accessTtl,
                           @Value("${vibepaper.jwt.refresh-ttl:604800}") long refreshTtl) {
        return new JwtUtil(secret, accessTtl, refreshTtl);
    }
}
