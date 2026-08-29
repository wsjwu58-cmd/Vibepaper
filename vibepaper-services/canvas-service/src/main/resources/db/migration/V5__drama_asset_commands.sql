-- 每次短剧资产写入的幂等命令快照，不能随资产更新覆盖。
CREATE TABLE drama_asset_commands (
    id                    BIGINT PRIMARY KEY,
    canvas_id             BIGINT       NOT NULL,
    idempotency_key       VARCHAR(128) NOT NULL,
    asset_id              BIGINT       NOT NULL,
    asset_type            VARCHAR(32)  NOT NULL,
    asset_version         INT          NOT NULL,
    result_canvas_version INT          NOT NULL,
    asset_data_snapshot   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_drama_asset_commands_canvas_key
    ON drama_asset_commands (canvas_id, idempotency_key);
