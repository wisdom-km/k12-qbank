-- R4 paper face. Old rows were not printed with a QR code.
-- The runner holds pg_advisory_xact_lock. This file does not.
-- Down drops the four columns. Stored face values are discarded.

ALTER TABLE papers ADD COLUMN qr_printed boolean NOT NULL DEFAULT false;

ALTER TABLE papers ADD COLUMN printed_external_id text NOT NULL DEFAULT '';

ALTER TABLE practice_item ADD COLUMN stem_text text NOT NULL DEFAULT '';

ALTER TABLE practice_item ADD COLUMN answer_text text NOT NULL DEFAULT '';
