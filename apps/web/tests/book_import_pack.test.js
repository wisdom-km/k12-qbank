import { describe, expect, it } from "vitest";
import { filesFromDataTransfer, filesFromInput, packBook } from "../src/book_import_pack.js";

function entry(path, text) {
  return { path, text };
}

function manifest(fields) {
  return entry("synth-folder/import-book.json", JSON.stringify(fields));
}

describe("packBook", () => {
  it("packs a three-directory book and skips backups, reviews, and answer sidecars", async () => {
    const result = await packBook([
      manifest({
        book_id: "synth-book",
        subject_id: "math",
        question_dir: "questions",
        answer_dir: "answers",
        toc_dir: "toc",
        toc_page_offset: 2,
        pairs: [{ answer_page: 1, question_page: 1 }],
      }),
      entry("synth-folder/questions/page_1.questions.json", JSON.stringify({ stem: "synth-stem", key: "1:1" })),
      entry("synth-folder/answers/page_1.answers/b.json", JSON.stringify({ text: "synth-answer-b" })),
      entry("synth-folder/answers/page_1.answers/a.json", JSON.stringify({ text: "synth-answer-a" })),
      entry("synth-folder/toc/page_4.md", "synth-toc-body"),
      entry("synth-folder/toc/notes.md", "synth-toc-skip"),
      entry("synth-folder/questions/_export_backups/page_8.questions.json", "{}"),
      entry("synth-folder/questions/_review_backups/page_9.questions.json", "{}"),
      entry("synth-folder/questions/_import_reports/page_10.questions.json", "{}"),
      entry("synth-folder/questions/page_11.reviewed.questions.json", "{}"),
      entry("synth-folder/questions/page_1.answers-meta.json", "{\"note\":\"synth-sidecar\"}"),
      entry("synth-folder/answers/page_1.answers/page_1.answers-meta.json", "{\"note\":\"synth-inside\"}"),
      entry("synth-folder/.hidden/page_12.questions.json", "{}"),
    ]);

    expect(result.ok).toBe(true);
    expect(result.bookId).toBe("synth-book");
    expect(result.summary).toEqual({
      book_id: "synth-book",
      subject_id: "math",
      question_pages: 1,
      answer_pages: 1,
      toc_pages: 1,
    });
    expect(result.body.subject_id).toBe("math");
    expect(result.body.pairing).toEqual([{ answer_page: 1, question_page: 1 }]);
    expect(result.body.toc_page_offset).toBe(2);
    expect(result.body.toc).toEqual([{ pdf_page: 4, text: "synth-toc-body" }]);
    expect(result.body.book_id).toBeUndefined();
    expect(result.body.pages).toEqual([
      {
        pdf_page: 1,
        role: "answers",
        volume: "answers",
        questions: null,
        answers: [{ text: "synth-answer-a" }, { text: "synth-answer-b" }],
      },
      {
        pdf_page: 1,
        role: "questions",
        volume: "questions",
        questions: { stem: "synth-stem", key: "1:1" },
        answers: [],
      },
    ]);
    expect(JSON.stringify(result.body.pages)).not.toContain("synth-sidecar");
    expect(JSON.stringify(result.body.pages)).not.toContain("synth-inside");
    expect(result.body.pages.map((page) => page.pdf_page)).toEqual([1, 1]);
  });

  it("marks an answer page that still has a question file and no answer directory", async () => {
    const result = await packBook([
      manifest({
        book_id: "synth-book",
        subject_id: "math",
        question_dir: "questions",
        answer_dir: "answers",
        pairs: [],
      }),
      entry("synth-folder/answers/page_2.questions.json", JSON.stringify({ stem: "synth-unmarked" })),
    ]);
    expect(result.ok).toBe(true);
    expect(result.body.pages).toEqual([
      {
        pdf_page: 2,
        role: "answers",
        volume: "answers",
        questions: null,
        answers: [],
        has_question_file: true,
      },
    ]);
  });

  it("uses page-role in a single directory and omits volume", async () => {
    const result = await packBook([
      entry(
        "import-book.json",
        JSON.stringify({ book_id: "synth-single", subject_id: "math", pairs: [] }),
      ),
      entry("page_1.questions.json", JSON.stringify({ stem: "synth-q" })),
      entry("page_2.page-role.txt", " answers \n"),
      entry("page_2.questions.json", JSON.stringify({ stem: "synth-left-behind" })),
      entry("page_2.answers/a.json", JSON.stringify({ text: "synth-a" })),
      entry("unit/PAGE_7.questions.json", JSON.stringify({ stem: "synth-page-seven" })),
      entry("page_2/page_10.questions.json", JSON.stringify({ stem: "synth-last-page" })),
    ]);
    expect(result.ok).toBe(true);
    expect(result.body.pages.map((page) => page.volume)).toEqual([undefined, undefined, undefined, undefined]);
    expect(result.body.pages.map((page) => [page.pdf_page, page.role])).toEqual([
      [1, "questions"],
      [2, "answers"],
      [7, "questions"],
      [10, "questions"],
    ]);
    expect(result.body.pages[1].answers).toEqual([{ text: "synth-a" }]);
    expect(JSON.stringify(result.body.pages[1])).not.toContain("synth-left-behind");
    expect(result.body.toc).toBeUndefined();
    expect(result.body.toc_page_offset).toBeUndefined();
  });

  it("copies an unknown manifest field into the request body", async () => {
    const result = await packBook([
      entry(
        "import-book.json",
        JSON.stringify({ book_id: "synth-book", subject_id: "math", pairs: [], vendor_note: "synth-note" }),
      ),
    ]);
    expect(result.ok).toBe(true);
    expect(result.body.vendor_note).toBe("synth-note");
    expect(result.body.pages).toEqual([]);
  });

  it("rejects a missing manifest, broken JSON, an absolute path, and a parent segment", async () => {
    const missing = await packBook([entry("page_1.questions.json", "{}")]);
    expect(missing.ok).toBe(false);
    expect(missing.message).toContain("import-book.json");

    const broken = await packBook([entry("import-book.json", "{")]);
    expect(broken.ok).toBe(false);
    expect(broken.message).toContain("语法不合法");

    const absolute = await packBook([
      entry("import-book.json", JSON.stringify({ book_id: "synth-book", question_dir: "/tmp/synth" })),
    ]);
    expect(absolute.ok).toBe(false);
    expect(absolute.message).toContain("question_dir");
    expect(absolute.message).toContain("绝对路径");

    const drive = await packBook([
      entry("import-book.json", JSON.stringify({ book_id: "synth-book", answer_dir: "C:\\synth" })),
    ]);
    expect(drive.ok).toBe(false);
    expect(drive.message).toContain("answer_dir");

    const parent = await packBook([
      entry("import-book.json", JSON.stringify({ book_id: "synth-book", toc_dir: "toc/../../etc" })),
    ]);
    expect(parent.ok).toBe(false);
    expect(parent.message).toContain("toc_dir");
    expect(parent.message).toContain("..");
  });

  it("reads a dropped folder, including a partial readEntries batch", async () => {
    const calls = [];
    const root = {
      name: "synth-folder",
      isFile: false,
      isDirectory: true,
      createReader() {
        const batches = [
          [
            {
              name: "import-book.json",
              isFile: true,
              isDirectory: false,
              file(ok) {
                ok(new File([JSON.stringify({ book_id: "synth-drop", subject_id: "math", pairs: [] })], "import-book.json"));
              },
            },
          ],
          [
            {
              name: "page_1.questions.json",
              isFile: true,
              isDirectory: false,
              file(ok) {
                ok(new File([JSON.stringify({ stem: "synth-drop-stem" })], "page_1.questions.json"));
              },
            },
          ],
        ];
        let index = 0;
        return {
          readEntries(ok) {
            calls.push(index);
            const batch = batches[index] || [];
            index += 1;
            ok(batch);
          },
        };
      },
    };
    const picked = await filesFromDataTransfer({
      items: [{ webkitGetAsEntry: () => root }],
    });
    const result = await packBook(picked);
    expect(calls).toEqual([0, 1, 2]);
    expect(result.ok).toBe(true);
    expect(result.bookId).toBe("synth-drop");
    expect(result.body.pages).toHaveLength(1);
    expect(result.body.pages[0].pdf_page).toBe(1);
    expect(result.body.pages[0].volume).toBeUndefined();
  });

  it("reads webkitRelativePath from a folder input", async () => {
    const file = new File(
      [JSON.stringify({ book_id: "synth-input", subject_id: "math", question_dir: "questions", pairs: [] })],
      "import-book.json",
    );
    Object.defineProperty(file, "webkitRelativePath", { value: "synth-folder/import-book.json" });
    const page = new File([JSON.stringify({ stem: "synth-input-stem" })], "page_3.questions.json");
    Object.defineProperty(page, "webkitRelativePath", { value: "synth-folder/questions/page_3.questions.json" });
    const result = await packBook(filesFromInput([file, page]));
    expect(result.ok).toBe(true);
    expect(result.body.pages).toEqual([
      {
        pdf_page: 3,
        role: "questions",
        volume: "questions",
        questions: { stem: "synth-input-stem" },
        answers: [],
      },
    ]);
  });
});
