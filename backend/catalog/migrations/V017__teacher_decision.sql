-- R7 teacher decisions. One current row per paper item. Old rows stay voided.
-- confirmations and issued papers are not rewritten.

CREATE TABLE teacher_decision (
    decision_id text PRIMARY KEY,
    paper_id text NOT NULL REFERENCES papers (paper_id),
    order_no integer NOT NULL,
    verdict text NOT NULL,
    source text NOT NULL,
    decided_by text NOT NULL,
    decided_at timestamptz NOT NULL,
    voided_at timestamptz NULL,
    ai_run_id text NULL,
    ai_verdict text NULL,
    ai_confidence double precision NULL,
    corrected_transcription text NULL,
    comment text NULL,
    CONSTRAINT teacher_decision_order CHECK (order_no >= 1),
    CONSTRAINT teacher_decision_verdict CHECK (verdict IN ('correct', 'incorrect', 'partial', 'blank')),
    CONSTRAINT teacher_decision_source CHECK (source IN ('adopted', 'revised', 'manual')),
    CONSTRAINT teacher_decision_ai_verdict CHECK (
        ai_verdict IS NULL OR ai_verdict IN ('correct', 'incorrect', 'partial', 'unsure')
    ),
    CONSTRAINT teacher_decision_ai_confidence CHECK (
        ai_confidence IS NULL OR (ai_confidence >= 0 AND ai_confidence <= 1)
    ),
    CONSTRAINT teacher_decision_ai_link CHECK (
        (
            source = 'manual'
            AND ai_run_id IS NULL
            AND ai_verdict IS NULL
            AND ai_confidence IS NULL
        )
        OR (
            source IN ('adopted', 'revised')
            AND ai_run_id IS NOT NULL
            AND ai_verdict IS NOT NULL
            AND ai_confidence IS NOT NULL
        )
    )
);

CREATE UNIQUE INDEX teacher_decision_current
    ON teacher_decision (paper_id, order_no)
    WHERE voided_at IS NULL;
