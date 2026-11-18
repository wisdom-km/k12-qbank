-- Bootstrap admin must change the startup password. Existing rows stay false.

ALTER TABLE users ADD COLUMN must_change_password boolean NOT NULL DEFAULT false;
