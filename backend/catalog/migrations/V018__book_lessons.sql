-- R4f books and lessons. Placement on approvals is nullable and is not backfilled.
-- No foreign key: an earlier down drops approvals while these tables still exist
-- only for the life of this version. Replacing lessons does not touch issued papers.

ALTER TABLE approvals ADD COLUMN book_id text;

ALTER TABLE approvals ADD COLUMN pdf_page integer;

CREATE TABLE book (
    book_id text PRIMARY KEY,
    subject_id text NOT NULL,
    imported_at timestamptz NOT NULL
);

CREATE TABLE book_lesson (
    book_id text NOT NULL,
    chapter_order integer NOT NULL,
    chapter_title text NOT NULL,
    section_title text NULL,
    lesson_order integer NOT NULL,
    lesson_title text NOT NULL,
    start_page integer NOT NULL,
    end_page integer NOT NULL,
    PRIMARY KEY (book_id, lesson_order),
    CONSTRAINT book_lesson_order CHECK (chapter_order >= 1 AND lesson_order >= 1),
    CONSTRAINT book_lesson_pages CHECK (start_page >= 1 AND end_page >= start_page)
);
