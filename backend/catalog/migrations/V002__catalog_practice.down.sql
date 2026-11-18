-- Reverse V002. schema_migrations stays; the runner deletes the version row.

DROP TABLE IF EXISTS confirmations;
DROP TABLE IF EXISTS attempts;
DROP TABLE IF EXISTS paper_pages;
DROP TABLE IF EXISTS papers;
DROP TABLE IF EXISTS files;
DROP TABLE IF EXISTS approvals;
