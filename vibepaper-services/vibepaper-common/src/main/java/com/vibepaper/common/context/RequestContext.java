package com.vibepaper.common.context;

/**
 * 请求上下文：从网关透传头（X-User-Id / X-User-Role / X-Enterprise-Id / X-Request-Id）解析。
 */
public final class RequestContext {
    public static final String HEADER_USER_ID = "X-User-Id";
    public static final String HEADER_USER_ROLE = "X-User-Role";
    public static final String HEADER_ENTERPRISE_ID = "X-Enterprise-Id";
    public static final String HEADER_REQUEST_ID = "X-Request-Id";

    private static final ThreadLocal<String> USER_ID = new ThreadLocal<>();
    private static final ThreadLocal<String> USER_ROLE = new ThreadLocal<>();
    private static final ThreadLocal<String> ENTERPRISE_ID = new ThreadLocal<>();
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    private RequestContext() {
    }

    public static void set(String userId, String role, String enterpriseId, String requestId) {
        USER_ID.set(userId);
        USER_ROLE.set(role);
        ENTERPRISE_ID.set(enterpriseId);
        REQUEST_ID.set(requestId);
    }

    public static void clear() {
        USER_ID.remove();
        USER_ROLE.remove();
        ENTERPRISE_ID.remove();
        REQUEST_ID.remove();
    }

    public static String userId() {
        return USER_ID.get();
    }

    public static Long userIdLong() {
        String v = USER_ID.get();
        return v == null || v.isBlank() ? null : Long.parseLong(v);
    }

    public static String role() {
        return USER_ROLE.get();
    }

    public static boolean isAdmin() {
        String role = USER_ROLE.get();
        return "ops_admin".equals(role) || "super_admin".equals(role);
    }

    public static String enterpriseId() {
        return ENTERPRISE_ID.get();
    }

    public static String requestId() {
        return REQUEST_ID.get();
    }
}
