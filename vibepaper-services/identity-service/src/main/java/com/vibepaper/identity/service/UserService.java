package com.vibepaper.identity.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.vibepaper.common.api.ApiException;
import com.vibepaper.common.context.RequestContext;
import com.vibepaper.identity.dto.AuthDtos;
import com.vibepaper.identity.entity.User;
import com.vibepaper.identity.entity.UserPreference;
import com.vibepaper.identity.mapper.UserMapper;
import com.vibepaper.identity.mapper.UserPreferenceMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserService {
    private final UserMapper userMapper;
    private final UserPreferenceMapper preferenceMapper;
    private final com.vibepaper.identity.feign.BillingClient billingClient;

    public Map<String, Object> getMe() {
        User user = currentUser();
        Map<String, Object> result = new HashMap<>();
        result.put("user", AuthService.toView(user));
        result.put("preferences", getPreference(user.getId()));
        try {
            Map<String, Object> account = billingClient.getAccount(user.getId());
            result.put("account", account);
        } catch (Exception e) {
            log.warn("fetch account failed: {}", e.getMessage());
            result.put("account", Map.of("balance", 0, "frozenPoints", 0, "availablePoints", 0));
        }
        return result;
    }

    @Transactional
    public AuthDtos.UserView updateProfile(AuthDtos.UpdateProfileRequest req) {
        User user = currentUser();
        if (req.nickname() != null && !req.nickname().isBlank()) {
            user.setNickname(req.nickname());
        }
        if (req.avatarUrl() != null) {
            user.setAvatarUrl(req.avatarUrl());
        }
        user.setUpdatedAt(OffsetDateTime.now());
        userMapper.updateById(user);
        return AuthService.toView(user);
    }

    public UserPreference getPreference(Long userId) {
        UserPreference pref = preferenceMapper.selectById(userId);
        if (pref == null) {
            pref = new UserPreference();
            pref.setUserId(userId);
            pref.setTheme("light");
            pref.setLanguage("zh");
            return pref;
        }
        return pref;
    }

    @Transactional
    public UserPreference updatePreference(AuthDtos.PreferenceRequest req) {
        Long userId = RequestContext.userIdLong();
        UserPreference pref = preferenceMapper.selectById(userId);
        if (pref == null) {
            pref = new UserPreference();
            pref.setUserId(userId);
        }
        if (req.theme() != null) {
            pref.setTheme(req.theme());
        }
        if (req.language() != null) {
            pref.setLanguage(req.language());
        }
        if (req.defaultTextModel() != null) {
            pref.setDefaultTextModel(req.defaultTextModel());
        }
        if (req.defaultImageModel() != null) {
            pref.setDefaultImageModel(req.defaultImageModel());
        }
        if (req.defaultVideoModel() != null) {
            pref.setDefaultVideoModel(req.defaultVideoModel());
        }
        if (req.defaultResolution() != null) {
            pref.setDefaultResolution(req.defaultResolution());
        }
        pref.setUpdatedAt(OffsetDateTime.now());
        if (preferenceMapper.selectById(userId) == null) {
            preferenceMapper.insert(pref);
        } else {
            preferenceMapper.updateById(pref);
        }
        return pref;
    }

    public User currentUser() {
        Long userId = RequestContext.userIdLong();
        if (userId == null) {
            throw ApiException.unauthorized("未登录");
        }
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw ApiException.notFound("用户不存在");
        }
        return user;
    }

    public User getById(Long userId) {
        return userMapper.selectById(userId);
    }

    public java.util.List<User> listByIds(java.util.Collection<Long> ids) {
        return userMapper.selectBatchIds(ids);
    }

    public User findOne(LambdaQueryWrapper<User> wrapper) {
        return userMapper.selectOne(wrapper);
    }

    public void save(User user) {
        userMapper.insert(user);
    }

    public void update(User user) {
        userMapper.updateById(user);
    }
}
