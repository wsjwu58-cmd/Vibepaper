package com.vibepaper.gallery;

import com.vibepaper.common.config.CommonConfig;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = {"com.vibepaper.common", "com.vibepaper.gallery"})
@EnableDiscoveryClient
@EnableFeignClients
@MapperScan("com.vibepaper.gallery.mapper")
@Import(CommonConfig.class)
public class GalleryApplication {
    public static void main(String[] args) {
        SpringApplication.run(GalleryApplication.class, args);
    }
}
