import { createRoot } from "react-dom/client";
import { act } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dropSession } from "../src/auth.js";
import { AppRoutes } from "../src/routes.jsx";

const admin = {
  role: "admin",
  display_name: "admin-one",
  csrf_token: "csrf-admin",
  actor_teacher_id: "admin-1",
  user_id: "admin-1",
  student_ids: [],
  question_version_id: "q-v1",
};

const pending = [];
let cleanup = () => {};

function jsonResponse(status, body, requestId) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (String(name).toLowerCase() === "x-request-id" ? requestId || "req-test" : null) },
    text: async () => JSON.stringify(body),
  };
}

function installFetch(handler) {
  pending.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (path, options) =>
        new Promise((resolve) => {
          pending.push(() => resolve(handler(String(path), options || {})));
        }),
    ),
  );
}

async function flush() {
  await act(async () => {
    const batch = pending.splice(0, pending.length);
    for (const run of batch) run();
    for (let step = 0; step < 12; step += 1) await Promise.resolve();
  });
}

async function renderAdmin() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
  });
  cleanup = () => {
    act(() => root.unmount());
    host.remove();
  };
}

async function settle(predicate) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (predicate()) return;
    await flush();
  }
  throw new Error(document.body.textContent);
}

function button(label) {
  return [...document.querySelectorAll("button")].find((item) => item.textContent === label);
}

function bookFile(path, text) {
  const file = new File([text], path.split("/").pop(), { type: "application/json" });
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

function assignFiles(input, files) {
  const list = {
    length: files.length,
    item: (index) => files[index] || null,
  };
  files.forEach((file, index) => {
    list[index] = file;
  });
  Object.defineProperty(input, "files", { configurable: true, value: list });
}

async function chooseFolder(files) {
  const input = document.querySelector("input[type=file]");
  assignFiles(input, files);
  await act(async () => {
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function threeDirFiles(bookId) {
  return [
    bookFile(
      "synth-folder/import-book.json",
      JSON.stringify({
        book_id: bookId,
        subject_id: "math",
        question_dir: "questions",
        answer_dir: "answers",
        toc_dir: "toc",
        toc_page_offset: 0,
        pairs: [{ answer_page: 1, question_page: 1 }],
      }),
    ),
    bookFile("synth-folder/questions/page_1.questions.json", JSON.stringify({ stem: "synth-stem", key: "1:1" })),
    bookFile("synth-folder/answers/page_1.answers/a.json", JSON.stringify({ text: "synth-answer" })),
    bookFile("synth-folder/toc/page_1.md", "synth-toc-body"),
  ];
}

function cleanReport(overrides) {
  return {
    book_id: "synth-book",
    dry_run: true,
    written: false,
    reason: "",
    pages: [
      { pdf_page: 1, role: "questions", outcome: "ok", reason: "", volume: "questions", hint: "" },
      { pdf_page: 1, role: "answers", outcome: "ok", reason: "", volume: "answers", hint: "" },
    ],
    questions: [
      {
        original_key: "1:1",
        key: "synth-book.p0001:1:1",
        question_version_id: "qv-synth",
        outcome: "staged",
        reason: "",
        lesson_order: 1,
      },
    ],
    staged: 1,
    kept: 0,
    skipped: 0,
    conflict: 0,
    space_changed: 0,
    toc_changed: false,
    toc_chapters: 1,
    toc_sections: 1,
    toc_lessons: 2,
    toc_unparsed: [{ pdf_page: 3, line: 4, text: "synth-hidden-line" }],
    ...overrides,
  };
}

function adminGets(path) {
  if (path === "/api/session") return jsonResponse(200, admin);
  if (path === "/api/account/sessions") return jsonResponse(200, { sessions: [] });
  if (path === "/api/admin/teachers") return jsonResponse(200, { teachers: [] });
  if (path === "/api/admin/students") return jsonResponse(200, { students: [] });
  if (path === "/api/admin/grants") return jsonResponse(200, { grants: [] });
  if (path === "/api/admin/errors") return jsonResponse(200, { errors: [] });
  if (path.startsWith("/api/admin/ai/accuracy")) {
    return jsonResponse(200, { current_threshold: 0.6, available_models: [], runs: { total: 0 }, items: { decided_total: 0 }, thresholds: [] });
  }
  return null;
}

describe("admin book import", () => {
  beforeEach(() => {
    dropSession();
    cleanup = () => {};
  });

  afterEach(() => {
    cleanup();
    cleanup = () => {};
    dropSession();
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  it("previews a chosen folder, then writes and refreshes the audit list", async () => {
    let wrote = false;
    installFetch((path, options) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path === "/api/admin/audit") {
        if (!wrote) return jsonResponse(200, { events: [] });
        return jsonResponse(200, {
          events: [{ action: "import_book", outcome: "ok", request_id: "req-write", occurred_at: "2026-11-25T00:00:00Z" }],
        });
      }
      if (path === "/api/admin/catalog/books/synth-book/import" && options.method === "POST") {
        const body = JSON.parse(options.body);
        expect(options.headers["X-K12-CSRF"]).toBe("csrf-admin");
        if (body.dry_run) return jsonResponse(200, cleanReport(), "req-preview");
        wrote = true;
        return jsonResponse(200, cleanReport({ dry_run: false, written: true, staged: 1 }), "req-write");
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("整书导入") && document.body.textContent.includes("老师"));
    expect(button("确认写入").disabled).toBe(true);
    await chooseFolder(threeDirFiles("synth-book"));
    await settle(() => document.body.textContent.includes("synth-book") && document.body.textContent.includes("题目页"));
    expect(document.body.textContent).not.toContain("synth-stem");
    expect(document.body.textContent).not.toContain("synth-answer");
    expect(document.body.textContent).not.toContain("synth-toc-body");
    expect(button("确认写入").disabled).toBe(true);

    await act(async () => {
      button("预演导入").click();
    });
    await settle(() => document.body.textContent.includes("预演未写入") && document.body.textContent.includes("req-preview"));
    expect(document.body.textContent).toContain("staged 1");
    expect(document.body.textContent).toContain("课时 2");
    expect(document.body.textContent).toContain("qv-synth");
    expect(document.body.textContent).toContain("pdf_page 3");
    expect(document.body.textContent).toContain("line 4");
    expect(document.body.textContent).not.toContain("synth-hidden-line");
    expect(document.body.textContent).not.toContain("synth-stem");
    expect(button("确认写入").disabled).toBe(false);

    await act(async () => {
      button("确认写入").click();
    });
    await settle(() => document.body.textContent.includes("已写入") && document.body.textContent.includes("import_book"));
    expect(document.body.textContent).toContain("req-write");
    const posts = fetch.mock.calls.filter((call) => call[0] === "/api/admin/catalog/books/synth-book/import");
    expect(JSON.parse(posts[0][1].body).dry_run).toBe(true);
    expect(JSON.parse(posts[1][1].body).dry_run).toBe(false);
    expect(posts[0][1].headers["X-K12-CSRF"]).toBe("csrf-admin");
    expect(posts[1][1].headers["X-K12-CSRF"]).toBe("csrf-admin");
    expect(JSON.parse(posts[0][1].body).pages).toHaveLength(2);
  });

  it("drops a folder and sends the same preview", async () => {
    installFetch((path, options) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path === "/api/admin/audit") return jsonResponse(200, { events: [] });
      if (path === "/api/admin/catalog/books/synth-book/import" && options.method === "POST") {
        return jsonResponse(200, cleanReport(), "req-drop");
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.querySelector(".book-drop"));
    const manifest = {
      name: "import-book.json",
      isFile: true,
      isDirectory: false,
      file(ok) {
        ok(
          new File(
            [
              JSON.stringify({
                book_id: "synth-book",
                subject_id: "math",
                question_dir: "questions",
                answer_dir: "answers",
                toc_dir: "toc",
                pairs: [],
              }),
            ],
            "import-book.json",
          ),
        );
      },
    };
    const question = {
      name: "page_1.questions.json",
      isFile: true,
      isDirectory: false,
      file(ok) {
        ok(new File([JSON.stringify({ stem: "synth-stem" })], "page_1.questions.json"));
      },
    };
    const root = {
      name: "synth-folder",
      isFile: false,
      isDirectory: true,
      createReader() {
        let pendingBatch = [manifest, directoryOf("questions", [question])];
        return {
          readEntries(ok) {
            const batch = pendingBatch;
            pendingBatch = [];
            ok(batch);
          },
        };
      },
    };
    const event = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: { items: [{ webkitGetAsEntry: () => root }] } });
    await act(async () => {
      document.querySelector(".book-drop").dispatchEvent(event);
    });
    await settle(() => document.body.textContent.includes("synth-book"));
    await act(async () => {
      button("预演导入").click();
    });
    await settle(() => document.body.textContent.includes("req-drop"));
    const post = fetch.mock.calls.find((call) => call[0] === "/api/admin/catalog/books/synth-book/import");
    expect(JSON.parse(post[1].body).dry_run).toBe(true);
    expect(post[1].headers["X-K12-CSRF"]).toBe("csrf-admin");
    expect(button("确认写入").disabled).toBe(false);
  });

  it("keeps confirm disabled when the preview marks an answer page or counts a conflict", async () => {
    let mode = "unmarked";
    installFetch((path, options) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path === "/api/admin/audit") return jsonResponse(200, { events: [] });
      if (String(path).endsWith("/import") && options.method === "POST") {
        if (mode === "unmarked") {
          return jsonResponse(
            200,
            cleanReport({
              pages: [
                {
                  pdf_page: 2,
                  role: "answers",
                  outcome: "rejected",
                  reason: "answer_page_not_marked",
                  volume: "answers",
                  hint: "synth-mark-the-answer-page",
                },
              ],
              questions: [],
              staged: 0,
              toc_lessons: 0,
              toc_chapters: 0,
              toc_sections: 0,
              toc_unparsed: [],
            }),
            "req-unmarked",
          );
        }
        return jsonResponse(200, cleanReport({ conflict: 2, staged: 0 }), "req-conflict");
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("整书导入"));
    await chooseFolder(threeDirFiles("synth-book"));
    await settle(() => document.body.textContent.includes("题目页"));
    await act(async () => {
      button("预演导入").click();
    });
    await settle(() => document.body.textContent.includes("answer_page_not_marked"));
    expect(document.body.textContent).toContain("synth-mark-the-answer-page");
    expect(document.body.textContent).toContain("已拒绝");
    expect(button("确认写入").disabled).toBe(true);

    mode = "conflict";
    await chooseFolder(threeDirFiles("synth-book"));
    await settle(() => !document.body.textContent.includes("answer_page_not_marked"));
    expect(button("确认写入").disabled).toBe(true);
    await act(async () => {
      button("预演导入").click();
    });
    await settle(() => document.body.textContent.includes("req-conflict"));
    expect(document.body.textContent).toContain("conflict 2");
    expect(document.body.textContent).toContain("已拒绝");
    expect(button("确认写入").disabled).toBe(true);
  });

  it("clears the previous preview when another folder is chosen", async () => {
    installFetch((path, options) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path === "/api/admin/audit") return jsonResponse(200, { events: [] });
      if (String(path).endsWith("/import") && options.method === "POST") {
        return jsonResponse(200, cleanReport(), "req-preview");
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("整书导入"));
    await chooseFolder(threeDirFiles("synth-book"));
    await settle(() => document.body.textContent.includes("synth-book"));
    await act(async () => {
      button("预演导入").click();
    });
    await settle(() => document.body.textContent.includes("req-preview"));
    expect(button("确认写入").disabled).toBe(false);
    await chooseFolder(threeDirFiles("synth-other"));
    await settle(() => document.body.textContent.includes("synth-other") && !document.body.textContent.includes("req-preview"));
    expect(button("确认写入").disabled).toBe(true);
    expect(document.body.textContent).not.toContain("预演未写入");
  });

  it("shows code, message, and request id for 403 and 409", async () => {
    let denied = true;
    installFetch((path, options) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path === "/api/admin/audit") return jsonResponse(200, { events: [] });
      if (String(path).endsWith("/import") && options.method === "POST") {
        if (denied) {
          return jsonResponse(403, { code: "permission_denied", message: "not an admin", request_id: "req-403" }, "req-header");
        }
        return jsonResponse(409, { code: "conflict", message: "book conflict", request_id: "req-409" }, "req-header");
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("整书导入"));
    await chooseFolder(threeDirFiles("synth-book"));
    await settle(() => document.body.textContent.includes("synth-book"));
    await act(async () => {
      button("预演导入").click();
    });
    await settle(() => document.body.textContent.includes("req-403"));
    expect(document.body.textContent).toContain("permission_denied");
    expect(document.body.textContent).toContain("not an admin");
    expect(button("确认写入").disabled).toBe(true);

    denied = false;
    await chooseFolder(threeDirFiles("synth-other"));
    await settle(() => document.body.textContent.includes("synth-other") && !document.body.textContent.includes("req-403"));
    await act(async () => {
      button("预演导入").click();
    });
    await settle(() => document.body.textContent.includes("req-409"));
    expect(document.body.textContent).toContain("conflict");
    expect(document.body.textContent).toContain("book conflict");
    expect(button("确认写入").disabled).toBe(true);
  });

  it("does not post when the manifest has no book id", async () => {
    installFetch((path) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path === "/api/admin/audit") return jsonResponse(200, { events: [] });
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("整书导入"));
    await chooseFolder([
      bookFile("synth-folder/import-book.json", JSON.stringify({ subject_id: "math", pairs: [] })),
    ]);
    await settle(() => document.body.textContent.includes("（空）"));
    const before = fetch.mock.calls.length;
    await act(async () => {
      button("预演导入").click();
    });
    await flush();
    expect(document.body.textContent).toContain("缺少 book_id");
    expect(fetch.mock.calls.length).toBe(before);
    expect(button("确认写入").disabled).toBe(true);
  });
});

function directoryOf(name, children) {
  return {
    name,
    isFile: false,
    isDirectory: true,
    createReader() {
      let pendingBatch = children;
      return {
        readEntries(ok) {
          const batch = pendingBatch;
          pendingBatch = [];
          ok(batch);
        },
      };
    },
  };
}
