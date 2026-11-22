-- Reverse V008. schema_migrations stays; the runner deletes the version row.
-- publication stays.

DELETE FROM publication_asset;
DROP TABLE publication_asset;
