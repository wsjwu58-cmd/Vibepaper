package com.vibepaper.common.api;

/**
 * 统一错误体：{ code, message, details, request_id, retryable }。
 */
public record ErrorResponse(String code, String message, Object details, String requestId, boolean retryable) {
    public static ErrorResponse of(String code, String message, Object details, String requestId, boolean retryable) {
        return new ErrorResponse(code, message, details, requestId, retryable);
    }
}
