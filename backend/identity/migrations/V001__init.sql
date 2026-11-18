-- Identity and audit tables. Identifiers are text. ADR 0028 and ADR 0029.

CREATE TABLE users (
    user_id text PRIMARY KEY,
    username text NOT NULL,
    role text NOT NULL,
    status text NOT NULL,
    password_hash text NOT NULL,
    password_algo text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    disabled_at timestamptz NULL,
    CONSTRAINT users_username_key UNIQUE (username),
    CONSTRAINT users_role_check CHECK (role IN ('admin', 'teacher')),
    CONSTRAINT users_status_check CHECK (status IN ('active', 'disabled'))
);

CREATE INDEX users_role_status ON users (role, status);

CREATE TABLE sessions (
    session_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users (user_id),
    csrf_token text NOT NULL,
    issued_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz NULL,
    user_agent_hash text NOT NULL DEFAULT '',
    ip_hash text NOT NULL DEFAULT ''
);

CREATE INDEX sessions_user_revoked ON sessions (user_id, revoked_at);
CREATE INDEX sessions_expires ON sessions (expires_at);

CREATE TABLE students (
    student_id text PRIMARY KEY,
    name text NOT NULL,
    grade text NOT NULL,
    subject_id text NOT NULL,
    status text NOT NULL,
    created_by text NOT NULL REFERENCES users (user_id),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT students_status_check CHECK (status IN ('active', 'archived'))
);

CREATE INDEX students_subject_status ON students (subject_id, status);

CREATE TABLE teacher_grants (
    grant_id text PRIMARY KEY,
    teacher_id text NOT NULL REFERENCES users (user_id),
    student_id text NOT NULL REFERENCES students (student_id),
    subject_id text NOT NULL,
    granted_by text NOT NULL REFERENCES users (user_id),
    granted_at timestamptz NOT NULL,
    revoked_at timestamptz NULL
);

CREATE UNIQUE INDEX teacher_grants_one_active
    ON teacher_grants (teacher_id, student_id, subject_id)
    WHERE revoked_at IS NULL;

CREATE TABLE login_attempts (
    attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username_hash text NOT NULL,
    ip_hash text NOT NULL,
    attempted_at timestamptz NOT NULL,
    outcome text NOT NULL,
    reason_code text NULL,
    CONSTRAINT login_attempts_outcome_check CHECK (outcome IN ('ok', 'fail'))
);

CREATE INDEX login_attempts_user_time ON login_attempts (username_hash, attempted_at);
CREATE INDEX login_attempts_ip_time ON login_attempts (ip_hash, attempted_at);

CREATE TABLE audit_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    request_id text NOT NULL,
    actor_user_id text NULL,
    actor_role text NULL,
    action text NOT NULL,
    target_kind text NULL,
    target_id text NULL,
    reason_code text NULL,
    outcome text NOT NULL,
    detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT audit_events_outcome_check CHECK (outcome IN ('ok', 'err'))
);

CREATE INDEX audit_events_time ON audit_events (occurred_at);
CREATE INDEX audit_events_actor_time ON audit_events (actor_user_id, occurred_at);
CREATE INDEX audit_events_action_time ON audit_events (action, occurred_at);
