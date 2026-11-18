-- Approved question and answer rows. Field names match the v1 draft files.
-- version is the kept history number. It is not schema_version.
-- One questions row is one item from the draft file's questions array.
-- Nested arrays stay jsonb. ADR 0013 and 0014 child tables are not created here.

CREATE TABLE questions (
    question_id text PRIMARY KEY,
    version integer NOT NULL,
    created_at timestamptz NOT NULL,
    approved_at timestamptz NOT NULL,
    contract text NOT NULL,
    contract_version integer NOT NULL,
    schema_version integer NOT NULL,
    ok boolean NOT NULL,
    reason text NOT NULL,
    preface text NOT NULL,
    source jsonb NOT NULL,
    key text NOT NULL,
    section text NOT NULL,
    number text NOT NULL,
    type text NOT NULL,
    structure text NOT NULL,
    status text NOT NULL,
    stem jsonb NOT NULL,
    options jsonb NOT NULL,
    subquestions jsonb NOT NULL,
    assets jsonb NOT NULL,
    geometry jsonb NULL,
    CONSTRAINT questions_version_check CHECK (version >= 1),
    CONSTRAINT questions_contract_check CHECK (contract = 'k12-question-draft'),
    CONSTRAINT questions_contract_version_check CHECK (contract_version = 1),
    CONSTRAINT questions_schema_version_check CHECK (schema_version = 1),
    CONSTRAINT questions_type_check CHECK (
        type IN (
            'single_choice',
            'multiple_choice',
            'fill_blank',
            'solution',
            'unresolved',
            'composite'
        )
    ),
    CONSTRAINT questions_structure_check CHECK (
        structure IN ('choice', 'blank', 'worked', 'unresolved', 'composite')
    ),
    CONSTRAINT questions_status_check CHECK (
        status IN ('candidate', 'needs_confirm', 'confirmed')
    ),
    CONSTRAINT questions_type_structure_check CHECK (
        (type = 'single_choice' AND structure = 'choice')
        OR (type = 'multiple_choice' AND structure = 'choice')
        OR (type = 'fill_blank' AND structure = 'blank')
        OR (type = 'solution' AND structure = 'worked')
        OR (type = 'unresolved' AND structure = 'unresolved')
        OR (type = 'composite' AND structure = 'composite')
    ),
    CONSTRAINT questions_key_version_key UNIQUE (key, version)
);

CREATE INDEX questions_key ON questions (key);

CREATE TABLE answers (
    answer_id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions (question_id),
    version integer NOT NULL,
    contract text NOT NULL,
    contract_version integer NOT NULL,
    schema_version integer NOT NULL,
    ok boolean NOT NULL,
    reason text NOT NULL,
    question_key text NOT NULL,
    key text NOT NULL,
    origin text NOT NULL,
    status text NOT NULL,
    applicable boolean NOT NULL,
    source jsonb NOT NULL,
    content jsonb NOT NULL,
    parts jsonb NOT NULL,
    assets jsonb NOT NULL,
    CONSTRAINT answers_version_check CHECK (version >= 1),
    CONSTRAINT answers_contract_check CHECK (contract = 'k12-answer-draft'),
    CONSTRAINT answers_contract_version_check CHECK (contract_version = 1),
    CONSTRAINT answers_schema_version_check CHECK (schema_version = 1),
    CONSTRAINT answers_origin_check CHECK (origin IN ('ocr', 'model', 'teacher')),
    CONSTRAINT answers_status_check CHECK (
        status IN ('candidate', 'needs_confirm', 'confirmed', 'disputed')
    ),
    CONSTRAINT answers_model_not_applicable CHECK (origin <> 'model' OR NOT applicable),
    CONSTRAINT answers_applicable_shape CHECK (
        NOT applicable OR (status = 'confirmed' AND ok)
    ),
    CONSTRAINT answers_key_version_key UNIQUE (key, version)
);

CREATE INDEX answers_question ON answers (question_id);

CREATE UNIQUE INDEX answers_one_applicable
    ON answers (question_key)
    WHERE applicable;
