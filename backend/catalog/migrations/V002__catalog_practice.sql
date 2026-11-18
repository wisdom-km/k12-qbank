-- Running catalog and practice rows. ADR 0039. Not the normalized question tables.

CREATE TABLE approvals (
    question_version_id text PRIMARY KEY,
    answer_version_id text NOT NULL,
    asset_ids text[] NOT NULL,
    layout_template_id text NOT NULL,
    question_approved boolean NOT NULL,
    answer_approved boolean NOT NULL,
    retired boolean NOT NULL,
    subject_id text NOT NULL,
    item_order text[] NOT NULL,
    stem text NOT NULL,
    answer_text text NOT NULL,
    CONSTRAINT approvals_answer_version_key UNIQUE (answer_version_id)
);

CREATE TABLE papers (
    paper_id text PRIMARY KEY,
    teacher_id text NOT NULL,
    student_id text NOT NULL,
    subject_id text NOT NULL,
    question_version_id text NOT NULL,
    answer_version_id text NOT NULL,
    asset_ids text[] NOT NULL,
    layout_template_id text NOT NULL,
    review_version_id text NOT NULL,
    file_id text NULL,
    status text NOT NULL,
    item_order text[] NOT NULL,
    file_checksum text NULL,
    formula text NOT NULL
);

CREATE TABLE paper_pages (
    paper_id text NOT NULL REFERENCES papers (paper_id),
    page_number integer NOT NULL,
    page_count integer NOT NULL,
    question_version_id text NOT NULL,
    answer_version_id text NOT NULL,
    formula text NOT NULL,
    student_id text NOT NULL,
    item_order text[] NOT NULL,
    asset_ids text[] NOT NULL,
    layout_template_id text NOT NULL,
    PRIMARY KEY (paper_id, page_number)
);

CREATE TABLE attempts (
    fixture_answer_id text PRIMARY KEY,
    paper_id text NOT NULL REFERENCES papers (paper_id),
    sub_question_id text NOT NULL,
    review_version_id text NOT NULL,
    student_id text NOT NULL,
    status text NOT NULL,
    answer_text text NOT NULL
);

CREATE TABLE confirmations (
    confirmation_id text PRIMARY KEY,
    operation_key text NOT NULL,
    paper_id text NOT NULL REFERENCES papers (paper_id),
    sub_question_id text NOT NULL,
    teacher_id text NOT NULL,
    review_version_id text NOT NULL,
    decision text NOT NULL,
    fixture_answer_id text NOT NULL,
    CONSTRAINT confirmations_scope_key UNIQUE (paper_id, sub_question_id, teacher_id, operation_key),
    CONSTRAINT confirmations_slot_key UNIQUE (paper_id, sub_question_id, review_version_id)
);

CREATE TABLE files (
    file_id text PRIMARY KEY,
    purpose text NOT NULL,
    checksum text NOT NULL
);
