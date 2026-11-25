import { createRoot } from "react-dom/client";
import { act } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dropSession } from "../src/auth.js";
import { AppRoutes } from "../src/routes.jsx";

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (String(name).toLowerCase() === "x-request-id" ? "req-test" : null) },
    text: async () => JSON.stringify(body),
  };
}

function catalogList() {
  return {
    items: [
      {
        question_version_id: "q-v1",
        subject_id: "math",
        stem: "(-3)+5",
        answer_text: "2",
        question_approved: false,
        answer_approved: false,
        retired: false,
      },
    ],
  };
}

const teacher = {
  role: "teacher",
  display_name: "teacher-synth",
  csrf_token: "csrf-test",
  actor_teacher_id: "teacher-synth",
  user_id: "teacher-synth",
  student_ids: ["student-synth"],
  question_version_id: "q-v1",
};

const pending = [];
let cleanup = () => {};

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

async function renderAt(path) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
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
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (predicate()) return;
    await flush();
  }
  throw new Error(document.body.textContent);
}

function setValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("session pages", () => {
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

  it("sends a teacher to the issue page after login", async () => {
    installFetch((path) => {
      if (path === "/api/login") return jsonResponse(200, teacher);
      if (path === "/api/session") return jsonResponse(200, teacher);
      if (path === "/api/catalog") return jsonResponse(200, catalogList());
      if (path.startsWith("/api/catalog/")) {
        return jsonResponse(200, {
          question_version_id: "q-v1",
          stem: "(-3)+5",
          answer_text: "2",
          question_approved: false,
          answer_approved: false,
          retired: false,
        });
      }
      if (path === "/api/practice/papers") return jsonResponse(200, { count: 0, papers: [] });
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/login");
    await settle(() => document.querySelector("input[name=username]"));
    await act(async () => {
      setValue(document.querySelector("input[name=username]"), "teacher-synth");
      setValue(document.querySelector("input[name=secret]"), "synth-pass1");
    });
    await act(async () => {
      document.querySelector("form").requestSubmit();
    });
    await settle(() => document.body.textContent.includes("有理数出卷"));
    expect(document.body.textContent).toContain("已登录：teacher teacher-synth");
    const loginCall = fetch.mock.calls.find((call) => call[0] === "/api/login");
    expect(JSON.parse(loginCall[1].body)).toEqual({ username: "teacher-synth", secret: "synth-pass1" });
  });

  it("shows the login failure and stays on the login page", async () => {
    installFetch((path) => {
      if (path === "/api/login") {
        return jsonResponse(401, { code: "unauthenticated", message: "sign in", request_id: "req-test" });
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/login");
    await settle(() => document.querySelector("form"));
    await act(async () => {
      setValue(document.querySelector("input[name=username]"), "teacher-synth");
      setValue(document.querySelector("input[name=secret]"), "not-the-one");
    });
    await act(async () => {
      document.querySelector("form").requestSubmit();
    });
    await settle(() => document.body.textContent.includes("unauthenticated：sign in"));
    expect(document.querySelector("h1").textContent).toBe("登录");
    expect(document.body.textContent).not.toContain("有理数出卷");
  });

  it("sends an anonymous admin visit to login", async () => {
    installFetch((path) => {
      if (path === "/api/session") {
        return jsonResponse(401, { code: "unauthenticated", message: "sign in", request_id: "req-test" });
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/admin");
    await settle(() => document.querySelector("h1") && document.querySelector("h1").textContent === "登录");
    expect(document.body.textContent).not.toContain("创建老师");
  });

  it("shows csrf when a write has no token", async () => {
    const signed = { ...teacher, csrf_token: "" };
    installFetch((path, options) => {
      const header = options.headers && options.headers["X-K12-CSRF"];
      if (path === "/api/logout") {
        if (!header) return jsonResponse(403, { code: "csrf", message: "csrf", request_id: "req-csrf" });
        return jsonResponse(200, { ok: true });
      }
      if (path === "/api/session") return jsonResponse(200, signed);
      if (path === "/api/catalog") return jsonResponse(200, catalogList());
      if (path.startsWith("/api/catalog/")) {
        return jsonResponse(200, {
          question_version_id: "q-v1",
          question_approved: false,
          answer_approved: false,
          retired: false,
        });
      }
      if (path === "/api/practice/papers") return jsonResponse(200, { count: 0, papers: [] });
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/");
    await settle(() => document.body.textContent.includes("注销"));
    await act(async () => {
      const button = [...document.querySelectorAll("button")].find((item) => item.textContent === "注销");
      button.click();
    });
    await settle(() => document.body.textContent.includes("csrf：csrf"));
    expect(document.body.textContent).toContain("req-csrf");
    expect(document.body.textContent).toContain("已登录：teacher teacher-synth");
    const logoutCall = fetch.mock.calls.find((call) => call[0] === "/api/logout");
    expect(logoutCall[1].headers["X-K12-CSRF"]).toBeUndefined();
  });

  it("opens the password page from the teacher header and clears the form", async () => {
    installFetch((path, options) => {
      if (path === "/api/session") return jsonResponse(200, teacher);
      if (path === "/api/account/password" && options.method === "POST") return jsonResponse(200, { ok: true });
      if (path === "/api/catalog") return jsonResponse(200, catalogList());
      if (path.startsWith("/api/catalog/")) {
        return jsonResponse(200, {
          question_version_id: "q-v1",
          question_approved: false,
          answer_approved: false,
          retired: false,
        });
      }
      if (path === "/api/practice/papers") return jsonResponse(200, { count: 0, papers: [] });
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/");
    await settle(() => document.body.textContent.includes("修改我的口令"));
    await act(async () => {
      const link = [...document.querySelectorAll("a")].find((item) => item.textContent === "修改我的口令");
      link.click();
    });
    await settle(() => document.querySelector("input[name=old_secret]"));
    await act(async () => {
      setValue(document.querySelector("input[name=old_secret]"), "old-secret9");
      setValue(document.querySelector("input[name=new_secret]"), "new-secret9");
    });
    await act(async () => {
      document.querySelector("form").requestSubmit();
    });
    await settle(() => document.body.textContent.includes("口令已更新"));
    expect(document.body.textContent).not.toContain("old-secret9");
    expect(document.body.textContent).not.toContain("new-secret9");
    expect(document.querySelector("input[name=old_secret]").value).toBe("");
    expect(document.querySelector("input[name=new_secret]").value).toBe("");
    const saved = fetch.mock.calls.find((call) => call[0] === "/api/account/password");
    expect(saved[1].headers["X-K12-CSRF"]).toBe("csrf-test");
    expect(JSON.parse(saved[1].body)).toEqual({ old_secret: "old-secret9", new_secret: "new-secret9" });
  });

  it("lists the admin's own sessions and revokes them in one click", async () => {
    const admin = {
      role: "admin",
      display_name: "admin-one",
      csrf_token: "csrf-admin",
      actor_teacher_id: "admin-1",
      user_id: "admin-1",
      student_ids: [],
      question_version_id: "q-v1",
    };
    let revoked = false;
    installFetch((path, options) => {
      if (revoked) return jsonResponse(401, { code: "unauthenticated", message: "sign in", request_id: "req-test" });
      if (path === "/api/admin/users/admin-1/sessions/revoke" && options.method === "POST") {
        revoked = true;
        return jsonResponse(200, { revoked: 1 });
      }
      if (path === "/api/session") return jsonResponse(200, admin);
      if (path === "/api/account/sessions") {
        return jsonResponse(200, {
          sessions: [
            {
              issued_at: "2026-11-18T08:00:00+00:00",
              last_seen_at: "2026-11-18T08:05:00+00:00",
              ip_hash_prefix: "abcdef01",
            },
          ],
        });
      }
      if (path === "/api/admin/teachers") return jsonResponse(200, { teachers: [] });
      if (path === "/api/admin/students") return jsonResponse(200, { students: [] });
      if (path === "/api/admin/grants") return jsonResponse(200, { grants: [] });
      if (path === "/api/admin/audit") return jsonResponse(200, { events: [] });
      if (path === "/api/admin/errors") return jsonResponse(200, { errors: [] });
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/admin");
    await settle(() => document.body.textContent.includes("活跃会话") && document.body.textContent.includes("abcdef01"));
    expect(document.body.textContent).toContain("2026-11-18T08:00:00+00:00");
    expect(document.body.textContent).toContain("2026-11-18T08:05:00+00:00");
    await act(async () => {
      const button = [...document.querySelectorAll("button")].find((item) => item.textContent === "一键吊销");
      button.click();
    });
    await settle(() => document.querySelector("h1") && document.querySelector("h1").textContent === "登录");
    const revokeCall = fetch.mock.calls.find((call) => call[0] === "/api/admin/users/admin-1/sessions/revoke");
    expect(revokeCall[1].method).toBe("POST");
    expect(revokeCall[1].headers["X-K12-CSRF"]).toBe("csrf-admin");
  });

  it("posts two chosen approved questions as one paper", async () => {
    const ready = (id, stem) => ({
      question_version_id: id,
      subject_id: "math",
      stem,
      answer_text: "2",
      question_approved: true,
      answer_approved: true,
      retired: false,
    });
    const rows = [ready("q-v1", "(-3)+5"), ready("q-v2", "2x3")];
    rows.push({
      question_version_id: "q-draft",
      subject_id: "math",
      stem: "draft",
      answer_text: "0",
      question_approved: false,
      answer_approved: false,
      retired: false,
    });
    installFetch((path, options) => {
      if (path === "/api/session") return jsonResponse(200, teacher);
      if (path === "/api/catalog") return jsonResponse(200, { items: rows });
      if (path === "/api/catalog/q-v1") return jsonResponse(200, rows[0]);
      if (path === "/api/catalog/q-v2") return jsonResponse(200, rows[1]);
      if (path === "/api/practice/papers" && options.method === "POST") {
        return jsonResponse(200, { paper_id: "paper-r4", status: "可打印", file_id: "file-r4" });
      }
      if (path === "/api/practice/papers/paper-r4/attempt") {
        return jsonResponse(200, {
          answer_text: "学生写下了 5",
          sub_question_id: "sq-1",
          review_version_id: "rev-1",
          fixture_answer_id: "fix-1",
        });
      }
      if (path === "/api/practice/papers") return jsonResponse(200, { count: 0, papers: [] });
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/");
    await settle(() => document.querySelectorAll('input[type="checkbox"]').length === 2);
    expect(document.body.textContent).toContain("q-draft");
    const boxes = [...document.querySelectorAll('input[type="checkbox"]')];
    await act(async () => {
      boxes[0].click();
    });
    await act(async () => {
      boxes[1].click();
    });
    await act(async () => {
      const button = [...document.querySelectorAll("button")].find((item) => item.textContent === "出卷");
      button.click();
    });
    await settle(() =>
      fetch.mock.calls.some((call) => call[0] === "/api/practice/papers" && call[1] && call[1].method === "POST"),
    );
    const posted = fetch.mock.calls.find(
      (call) => call[0] === "/api/practice/papers" && call[1] && call[1].method === "POST",
    );
    expect(JSON.parse(posted[1].body).items).toEqual([
      { question_version_id: "q-v1" },
      { question_version_id: "q-v2" },
    ]);
  });

  it("selects every issuable question in one lesson", async () => {
    const ready = (id, extra) => ({
      question_version_id: id,
      subject_id: "math",
      stem: "synth-stem",
      answer_text: "2",
      question_approved: true,
      answer_approved: true,
      retired: false,
      book_id: "synth-r4f",
      chapter_title: "synth-ch",
      section_title: "synth-sec",
      lesson_title: "synth-les",
      lesson_order: 1,
      pdf_page: 1,
      ...extra,
    });
    const rows = [
      ready("q-les-1", {}),
      ready("q-les-2", {}),
      ready("q-les-bad", { formula_note: "公式未结构化" }),
      ready("q-les-draft", { question_approved: false, answer_approved: false }),
      ready("q-loose", { book_id: "", lesson_order: 0 }),
    ];
    installFetch((path) => {
      if (path === "/api/session") return jsonResponse(200, teacher);
      if (path === "/api/catalog") return jsonResponse(200, { items: rows });
      if (path.startsWith("/api/catalog/")) {
        const id = path.slice("/api/catalog/".length);
        return jsonResponse(200, rows.find((item) => item.question_version_id === id) || rows[0]);
      }
      if (path === "/api/practice/papers") return jsonResponse(200, { count: 0, papers: [] });
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-test" });
    });
    await renderAt("/");
    await settle(() => document.querySelectorAll('input[type="checkbox"]').length === 1);
    expect(document.body.textContent).toContain("未归类");
    expect(document.body.textContent).toContain("synth-r4f");
    const lesson = [...document.querySelectorAll(".lesson-block")].find((block) =>
      block.textContent.includes("课时 1"),
    );
    expect(lesson.textContent).toContain("2 道可出卷");
    await act(async () => {
      [...lesson.querySelectorAll("button")].find((item) => item.textContent.startsWith("展开")).click();
    });
    await act(async () => {
      [...lesson.querySelectorAll("button")].find((item) => item.textContent === "选中本课时全部可出卷的题").click();
    });
    const checked = [...lesson.querySelectorAll('input[type="checkbox"]')].filter((box) => box.checked);
    expect(checked).toHaveLength(2);
    expect(lesson.textContent).toContain("q-les-bad");
    const bad = [...lesson.querySelectorAll("li")].find((item) => item.textContent.includes("q-les-bad"));
    expect(bad.querySelector('input[type="checkbox"]').checked).toBe(false);
  });
});
