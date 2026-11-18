-- Reverse V001. schema_migrations stays; the runner deletes the version row.

DROP TABLE IF EXISTS audit_events;
DROP TABLE IF EXISTS login_attempts;
DROP TABLE IF EXISTS teacher_grants;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS users;
