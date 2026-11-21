-- Reverse V006. schema_migrations stays; the runner deletes the version row.
-- papers, paper_pages, and confirmations stay.

DROP TABLE IF EXISTS practice_item;
