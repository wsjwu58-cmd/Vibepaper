package com.vibepaper.common.api;

/**
 * 稳定错误码（PRD §10.2）。
 */
public final class ErrorCode {
    private ErrorCode() {
    }

    public static final String INSUFFICIENT_POINTS = "INSUFFICIENT_POINTS";
    public static final String MODEL_TIMEOUT = "MODEL_TIMEOUT";
    public static final String MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE";
    public static final String CONTENT_BLOCKED = "CONTENT_BLOCKED";
    public static final String INVALID_INPUT = "INVALID_INPUT";
    public static final String FREEZE_EXPIRED = "FREEZE_EXPIRED";
    public static final String VERSION_CONFLICT = "VERSION_CONFLICT";
    public static final String PERMISSION_DENIED = "PERMISSION_DENIED";
    public static final String NOT_FOUND = "NOT_FOUND";
    public static final String DUPLICATE = "DUPLICATE";
    public static final String RATE_LIMITED = "RATE_LIMITED";
    public static final String UNAUTHORIZED = "UNAUTHORIZED";
    public static final String INTERNAL_ERROR = "INTERNAL_ERROR";
    public static final String TASK_STATE_INVALID = "TASK_STATE_INVALID";
    public static final String BILLING_ERROR = "BILLING_ERROR";
    public static final String AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED";
    public static final String SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE";
    public static final String EDGE_INVALID = "EDGE_INVALID";
    public static final String CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED";
    public static final String CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED";
    public static final String FILE_TOO_LARGE = "FILE_TOO_LARGE";
    public static final String FILE_TYPE_INVALID = "FILE_TYPE_INVALID";
}
