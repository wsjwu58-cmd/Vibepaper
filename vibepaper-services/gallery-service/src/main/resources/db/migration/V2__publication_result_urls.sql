ALTER TABLE publications
    ADD COLUMN IF NOT EXISTS result_asset_urls TEXT;
