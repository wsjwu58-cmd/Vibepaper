package com.vibepaper.identity.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.identity.dto.AuthDtos;
import com.vibepaper.identity.entity.User;
import com.vibepaper.identity.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * 内部接口服务：供其他微服务（admin 等）使用，不对外暴露。
 */
@Service
@RequiredArgsConstructor
public class InternalService {
    private final UserMapper userMapper;

    public AuthDtos.UserView getUser(Long userId) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw ApiException.notFound("用户不存在");
        }
        return AuthService.toView(user);
    }

    public AuthDtos.UserView getByEmail(String email) {
        User user = userMapper.selectOne(new LambdaQueryWrapper<User>().eq(User::getEmail, email.toLowerCase().trim()));
        if (user == null) {
            throw ApiException.notFound("用户不存在");
        }
        return AuthService.toView(user);
    }

    public void updateStatus(Long userId, String status) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw ApiException.notFound("用户不存在");
        }
        user.setStatus(status);
        userMapper.updateById(user);
    }

    public List<AuthDtos.UserView> list(List<Long> ids) {
        return userMapper.selectBatchIds(ids).stream().map(AuthService::toView).toList();
    }

    public Map<String, Object> page(String keyword, String status, int page, int pageSize) {
        LambdaQueryWrapper<User> qw = new LambdaQueryWrapper<User>()
                .and(keyword != null && !keyword.isBlank(), w -> w
                        .like(User::getNickname, keyword)
                        .or().like(User::getEmail, keyword)
                        .or().eq(User::getId, keyword != null && keyword.matches("\\d+") ? Long.parseLong(keyword) : -1L))
                .eq(status != null && !status.isBlank(), User::getStatus, status)
                .orderByDesc(User::getCreatedAt);
        com.baomidou.mybatisplus.extension.plugins.pagination.Page<User> p =
                new com.baomidou.mybatisplus.extension.plugins.pagination.Page<>(page, pageSize);
        var result = userMapper.selectPage(p, qw);
        return Map.of("items", result.getRecords().stream().map(AuthService::toView).toList(),
                "total", result.getTotal(), "page", page, "pageSize", pageSize);
    }
}
