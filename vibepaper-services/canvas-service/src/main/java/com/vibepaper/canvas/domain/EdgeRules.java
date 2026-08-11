package com.vibepaper.canvas.domain;

import java.util.Map;
import java.util.Set;

/**
 * 连线兼容性规则（PRD §6.1.2 / AC-07）。
 * 行 = 上游 source 类型；列 = 下游 target 类型。
 * 左侧输入、右侧输出。
 */
public final class EdgeRules {
    private EdgeRules() {
    }

    private static final Map<String, Set<String>> COMPAT = Map.of(
            "text", Set.of("text", "image", "video", "audio", "director"),
            "image", Set.of("image", "video", "director"),
            "video", Set.of("video", "compose"),
            "audio", Set.of("audio", "video"),
            "compose", Set.of("video", "compose"),
            "director", Set.of("image", "video")
    );

    public static boolean isCompatible(String sourceType, String targetType) {
        Set<String> targets = COMPAT.get(sourceType);
        return targets != null && targets.contains(targetType);
    }

    public static boolean isValidNodeType(String type) {
        return COMPAT.containsKey(type);
    }
}
