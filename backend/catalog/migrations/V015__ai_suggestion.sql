-- R6 recognition runs and suggestions. Confirmations stay untouched.

CREATE TABLE ai_run (
    run_id text PRIMARY KEY,
    intake_id text NOT NULL REFERENCES intake_page (intake_id),
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    status text NOT NULL,
    error_code text NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NULL,
    input_tokens integer NULL,
    output_tokens integer NULL,
    external_match text NULL,
    page_match text NULL,
    CONSTRAINT ai_run_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    CONSTRAINT ai_run_external_match CHECK (
        external_match IS NULL OR external_match IN ('consistent', 'mismatch', 'unread')
    ),
    CONSTRAINT ai_run_page_match CHECK (
        page_match IS NULL OR page_match IN ('consistent', 'mismatch', 'unread')
    )
);

CREATE UNIQUE INDEX ai_run_active
    ON ai_run (intake_id)
    WHERE status IN ('queued', 'running');

CREATE TABLE ai_suggestion (
    run_id text NOT NULL REFERENCES ai_run (run_id),
    paper_id text NOT NULL REFERENCES papers (paper_id),
    order_no integer NOT NULL,
    transcription text NOT NULL,
    unreadable boolean NOT NULL,
    confidence double precision NOT NULL,
    verdict text NOT NULL,
    reason text NOT NULL,
    judged_by text NOT NULL,
    PRIMARY KEY (run_id, order_no),
    CONSTRAINT ai_suggestion_verdict CHECK (verdict IN ('correct', 'incorrect', 'partial', 'unsure')),
    CONSTRAINT ai_suggestion_judged_by CHECK (judged_by IN ('local', 'model')),
    CONSTRAINT ai_suggestion_confidence CHECK (confidence >= 0 AND confidence <= 1)
);
