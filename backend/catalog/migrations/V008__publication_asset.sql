-- Publication files. ADR 0015 item 5 continued.
-- The runner holds pg_advisory_xact_lock. This file does not.
-- file_id shape is checked here. The kind-to-mime map lives in code.
-- No uri, no storage_backend, and no retired column on this table.
-- Retire does not change these rows. A new publication starts with none.

CREATE TABLE publication_asset (
    publication_asset_id text PRIMARY KEY,
    publication_id text NOT NULL REFERENCES publication (publication_id) ON DELETE RESTRICT,
    file_id text NOT NULL,
    kind text NOT NULL,
    checksum text NOT NULL,
    size_bytes bigint NOT NULL,
    mime_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    CONSTRAINT publication_asset_id_shape CHECK (publication_asset_id ~ '^pubasset-[0-9a-f]{16}$'),
    CONSTRAINT publication_asset_file_id_shape CHECK (file_id ~ '^pubfile-[0-9a-f]{16}$'),
    CONSTRAINT publication_asset_kind_known CHECK (kind IN ('image', 'pdf')),
    CONSTRAINT publication_asset_size_nonneg CHECK (size_bytes >= 0),
    CONSTRAINT publication_asset_publication_checksum UNIQUE (publication_id, checksum)
);

CREATE INDEX publication_asset_by_publication ON publication_asset (publication_id);
