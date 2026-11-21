-- Multi-item practice rows. ADR 0015 item 7.
-- papers, paper_pages, and confirmations stay as they are.
-- No foreign key to questions or answers.
-- score stays null when there is no institution rule.
-- order_no is the sequence. ORDER is reserved.

CREATE TABLE practice_item (
    paper_id text NOT NULL REFERENCES papers (paper_id),
    order_no integer NOT NULL,
    question_version_id text NOT NULL,
    answer_version_id text NOT NULL,
    score integer NULL,
    PRIMARY KEY (paper_id, order_no)
);
