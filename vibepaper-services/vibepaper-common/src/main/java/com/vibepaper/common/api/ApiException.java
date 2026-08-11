package com.vibepaper.common.api;

import lombok.Getter;
import org.springframework.http.HttpStatus;

/**
 * 业务异常，携带稳定错误码与可重试标记。
 */
@Getter
public class ApiException extends RuntimeException {
    private final String code;
    private final Object details;
    private final boolean retryable;
    private final HttpStatus httpStatus;

    public ApiException(String code, String message) {
        this(code, message, null, false, HttpStatus.BAD_REQUEST);
    }

    public ApiException(String code, String message, boolean retryable) {
        this(code, message, null, retryable, HttpStatus.BAD_REQUEST);
    }

    public ApiException(String code, String message, Object details, boolean retryable, HttpStatus httpStatus) {
        super(message);
        this.code = code;
        this.details = details;
        this.retryable = retryable;
        this.httpStatus = httpStatus;
    }

    public static ApiException badRequest(String code, String message) {
        return new ApiException(code, message, null, false, HttpStatus.BAD_REQUEST);
    }

    public static ApiException notFound(String message) {
        return new ApiException(ErrorCode.NOT_FOUND, message, null, false, HttpStatus.NOT_FOUND);
    }

    public static ApiException unauthorized(String message) {
        return new ApiException(ErrorCode.UNAUTHORIZED, message, null, false, HttpStatus.UNAUTHORIZED);
    }

    public static ApiException forbidden(String message) {
        return new ApiException(ErrorCode.PERMISSION_DENIED, message, null, false, HttpStatus.FORBIDDEN);
    }

    public static ApiException conflict(String code, String message) {
        return new ApiException(code, message, null, true, HttpStatus.CONFLICT);
    }
}
