-- Child rows of an approved question or answer. Draft field names stay as written.
-- V004 already has type and structure on questions. This file does not alter it.
-- figure_geometry and answer_decision stay unbuilt.
-- One questions row is still one draft item. Nested fragment arrays stay jsonb.
-- position keeps the array order. The draft files do not name that field.
-- A question_option with a null sub_question_id belongs to the question itself.

CREATE TABLE sub_question (
    sub_question_id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions (question_id),
    position integer NOT NULL,
    number text NOT NULL,
    stem jsonb NOT NULL,
    type text NULL,
    structure text NULL,
    CONSTRAINT sub_question_position_check CHECK (position >= 1),
    CONSTRAINT sub_question_stem_check CHECK (jsonb_typeof(stem) = 'array'),
    CONSTRAINT sub_question_id_question_key UNIQUE (sub_question_id, question_id),
    CONSTRAINT sub_question_question_position_key UNIQUE (question_id, position),
    CONSTRAINT sub_question_type_pair_check CHECK (
        (type IS NULL AND structure IS NULL)
        OR (type = 'single_choice' AND structure = 'choice')
        OR (type = 'multiple_choice' AND structure = 'choice')
        OR (type = 'fill_blank' AND structure = 'blank')
        OR (type = 'solution' AND structure = 'worked')
    )
);

CREATE INDEX sub_question_question ON sub_question (question_id);

CREATE TABLE question_option (
    question_option_id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions (question_id),
    sub_question_id text NULL,
    position integer NOT NULL,
    key text NOT NULL,
    content jsonb NOT NULL,
    CONSTRAINT question_option_position_check CHECK (position >= 1),
    CONSTRAINT question_option_key_check CHECK (key IN ('A', 'B', 'C', 'D')),
    CONSTRAINT question_option_content_check CHECK (jsonb_typeof(content) = 'array'),
    CONSTRAINT question_option_sub_question_fkey
        FOREIGN KEY (sub_question_id, question_id)
        REFERENCES sub_question (sub_question_id, question_id)
);

CREATE UNIQUE INDEX question_option_on_question_key
    ON question_option (question_id, key)
    WHERE sub_question_id IS NULL;

CREATE UNIQUE INDEX question_option_on_question_position
    ON question_option (question_id, position)
    WHERE sub_question_id IS NULL;

CREATE UNIQUE INDEX question_option_on_sub_key
    ON question_option (sub_question_id, key)
    WHERE sub_question_id IS NOT NULL;

CREATE UNIQUE INDEX question_option_on_sub_position
    ON question_option (sub_question_id, position)
    WHERE sub_question_id IS NOT NULL;

CREATE INDEX question_option_question ON question_option (question_id);

CREATE TABLE question_asset (
    question_asset_id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions (question_id),
    position integer NOT NULL,
    role text NOT NULL,
    bbox jsonb NOT NULL,
    CONSTRAINT question_asset_position_check CHECK (position >= 1),
    CONSTRAINT question_asset_role_check CHECK (role = 'crop'),
    CONSTRAINT question_asset_bbox_check CHECK (
        jsonb_typeof(bbox) = 'array'
        AND jsonb_array_length(bbox) = 4
        AND jsonb_typeof(bbox -> 0) = 'number'
        AND jsonb_typeof(bbox -> 1) = 'number'
        AND jsonb_typeof(bbox -> 2) = 'number'
        AND jsonb_typeof(bbox -> 3) = 'number'
    ),
    CONSTRAINT question_asset_question_position_key UNIQUE (question_id, position)
);

CREATE INDEX question_asset_question ON question_asset (question_id);

CREATE TABLE answer_part (
    answer_part_id text PRIMARY KEY,
    answer_id text NOT NULL REFERENCES answers (answer_id),
    sub_key text NOT NULL,
    role text NOT NULL,
    "order" integer NOT NULL,
    content jsonb NOT NULL,
    CONSTRAINT answer_part_role_check CHECK (role IN ('result', 'step')),
    CONSTRAINT answer_part_order_check CHECK ("order" >= 1),
    CONSTRAINT answer_part_content_check CHECK (
        jsonb_typeof(content) = 'array' AND jsonb_array_length(content) >= 1
    ),
    CONSTRAINT answer_part_answer_order_key UNIQUE (answer_id, "order")
);

CREATE INDEX answer_part_answer ON answer_part (answer_id);

CREATE TABLE answer_asset (
    answer_asset_id text PRIMARY KEY,
    answer_id text NOT NULL REFERENCES answers (answer_id),
    position integer NOT NULL,
    role text NOT NULL,
    bbox jsonb NOT NULL,
    CONSTRAINT answer_asset_position_check CHECK (position >= 1),
    CONSTRAINT answer_asset_role_check CHECK (role = 'crop'),
    CONSTRAINT answer_asset_bbox_check CHECK (
        jsonb_typeof(bbox) = 'array'
        AND jsonb_array_length(bbox) = 4
        AND jsonb_typeof(bbox -> 0) = 'number'
        AND jsonb_typeof(bbox -> 1) = 'number'
        AND jsonb_typeof(bbox -> 2) = 'number'
        AND jsonb_typeof(bbox -> 3) = 'number'
    ),
    CONSTRAINT answer_asset_answer_position_key UNIQUE (answer_id, position)
);

CREATE INDEX answer_asset_answer ON answer_asset (answer_id);

-- The approval snapshot can name a real type. Empty stays null.
-- questions.type is not rewritten here. A later script may copy this pair.

ALTER TABLE approvals ADD COLUMN type text;
ALTER TABLE approvals ADD COLUMN structure text;
ALTER TABLE approvals ADD CONSTRAINT approvals_type_structure_check CHECK (
    (type IS NULL AND structure IS NULL)
    OR (type = 'single_choice' AND structure = 'choice')
    OR (type = 'multiple_choice' AND structure = 'choice')
    OR (type = 'fill_blank' AND structure = 'blank')
    OR (type = 'solution' AND structure = 'worked')
    OR (type = 'unresolved' AND structure = 'unresolved')
    OR (type = 'composite' AND structure = 'composite')
);
