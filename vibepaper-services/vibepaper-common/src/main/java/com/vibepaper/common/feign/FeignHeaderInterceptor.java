package com.vibepaper.common.feign;

import com.vibepaper.common.context.RequestContext;
import feign.RequestInterceptor;
import feign.RequestTemplate;

/**
 * Feign 调用时透传身份与请求 ID，保证内部调用上下文一致。
 */
public class FeignHeaderInterceptor implements RequestInterceptor {

    @Override
    public void apply(RequestTemplate template) {
        if (RequestContext.userId() != null) {
            template.header(RequestContext.HEADER_USER_ID, RequestContext.userId());
        }
        if (RequestContext.role() != null) {
            template.header(RequestContext.HEADER_USER_ROLE, RequestContext.role());
        }
        if (RequestContext.enterpriseId() != null) {
            template.header(RequestContext.HEADER_ENTERPRISE_ID, RequestContext.enterpriseId());
        }
        if (RequestContext.requestId() != null) {
            template.header(RequestContext.HEADER_REQUEST_ID, RequestContext.requestId());
        }
    }
}
