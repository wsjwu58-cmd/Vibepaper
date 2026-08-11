package com.vibepaper.asset.dto;

import java.time.OffsetDateTime;

public final class AssetDtos {
    private AssetDtos() {
    }

    public record AssetView(Long id, Long ownerId, String name, String assetType, String mimeType,
                            Long sizeBytes, String url, String thumbnailUrl, String status,
                            Long enterpriseId, String certificationStatus, String certificationReason,
                            String createdAt, String updatedAt) {
    }

    public record ReferenceView(Long canvasId, Long nodeId, String refType) {
    }
}
