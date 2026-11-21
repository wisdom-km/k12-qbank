-- Reverse V007. schema_migrations stays; the runner deletes the version row.
-- Other tables stay.

DELETE FROM publication;
DROP TABLE publication;
