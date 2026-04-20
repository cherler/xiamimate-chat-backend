-- Site-level configuration (admin-editable key-value pairs).

CREATE TABLE IF NOT EXISTS app.site_config (
    config_key    TEXT PRIMARY KEY,
    config_value  TEXT NOT NULL DEFAULT '',
    display_name  TEXT NOT NULL DEFAULT '',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
