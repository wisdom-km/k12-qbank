import { createRoot } from "react-dom/client";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { GradePage } from "../src/grade_page.jsx";
import { TeacherPage } from "../src/teacher_page.jsx";

const { mockCall } = vi.hoisted(() => ({ mockCall: vi.fn() }));

vi.mock("../src/auth.js", () => ({
  call: (...args) => mockCall(...args),
}));

let cleanup = () => {};

afterEach(() => {
  cleanup();
  cleanup = () => {};
  mockCall.mockReset();
});

function decision(verdict) {
  return { verdict, source: "manual", comment: "" };
}

function item(orderNo, extra) {
  return {
    order_no: orderNo,
    question_type: "solution",
    stem: "synth-r8-stem",
    standard_answer: "synth-a",
    page_no: 1,
    intake_status: "missing",
    stale: false,
    suggestion: null,
    decision: null,
    ...extra,
  };
}

function review(items) {
  return {
    paper_id: "paper-synth-r8",
    threshold: 0.6,
    confirmed: items.filter((row) => row.decision).length,
    total: items.length,
    correct: items.filter((row) => row.decision && row.decision.verdict === "correct").length,
    done: false,
    mismatch_pages: [],
    items,
  };
}

const mixed = review([
  item(1, { decision: decision("incorrect"), suggestion: { verdict: "incorrect", transcription: "synth", confidence: 0.2, judged_by: "model", needs_review: true, unreadable: false, reason: "synth", run_id: "run-synth" } }),
  item(2, { decision: decision("correct") }),
  item(3, { decision: decision("partial") }),
  item(4, { decision: decision("blank") }),
  item(5, { suggestion: { verdict: "incorrect", transcription: "synth", confidence: 0.9, judged_by: "model", needs_review: false, unreadable: false, reason: "synth", run_id: "run-synth" } }),
]);

async function renderGrade(body, call) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <GradePage paperId="paper-synth-r8" call={call || (async () => body)} />
      </MemoryRouter>,
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  cleanup = () => {
    act(() => root.unmount());
    host.remove();
  };
  return host;
}

function box(host, orderNo) {
  return host.querySelector('[aria-label="再练题 ' + orderNo + '"]');
}

describe("follow-up on the grade page", () => {
  it("checks incorrect, partial, and blank, and leaves correct and unconfirmed alone", async () => {
    const host = await renderGrade(mixed);
    expect(box(host, 1).checked).toBe(true);
    expect(box(host, 2).checked).toBe(false);
    expect(box(host, 3).checked).toBe(true);
    expect(box(host, 4).checked).toBe(true);
    expect(box(host, 5)).toBeNull();
  });

  it("sends the remaining order numbers and can hand out the new paper", async () => {
    const calls = [];
    const host = await renderGrade(mixed, async (path, options) => {
      calls.push({ path, options });
      if (String(path).endsWith("/follow-up")) {
        return {
          paper_id: "paper-synth-r8-new",
          file_id: "file-synth-r8",
          status: "可打印",
          source_paper_id: "paper-synth-r8",
        };
      }
      if (String(path).endsWith("/handout")) {
        return {
          paper_id: "paper-synth-r8-new",
          file_id: "file-synth-r8",
          status: "已发放",
          source_paper_id: "paper-synth-r8",
        };
      }
      return mixed;
    });
    const second = box(host, 1);
    await act(async () => {
      second.click();
    });
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "再出一份练习");
    await act(async () => {
      button.click();
    });
    const sent = calls.find((row) => row.path.endsWith("/follow-up"));
    expect(JSON.parse(sent.options.body).order_nos).toEqual([3, 4]);
    expect(host.textContent).toContain("新卷号 paper-synth-r8-new");
    expect(host.textContent).toContain("包含 2 题");
    const pdf = [...host.querySelectorAll("a")].find((item) => item.textContent === "打开 PDF");
    expect(pdf.getAttribute("href")).toBe("/api/practice/files/file-synth-r8");
    const hand = [...host.querySelectorAll("button")].find((item) => item.textContent === "正式发放");
    await act(async () => {
      hand.click();
    });
    expect(calls.some((row) => row.path === "/api/practice/papers/paper-synth-r8-new/handout")).toBe(true);
    expect(host.textContent).toContain("状态 已发放");
    expect(host.textContent).toContain("返回老师页");
  });

  it("disables the button when nothing confirmed is still wrong", async () => {
    const correct = review([item(1, { decision: decision("correct") })]);
    const host = await renderGrade(correct);
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "再出一份练习");
    expect(button.disabled).toBe(true);
    expect(host.textContent).toContain("暂无可再练的已确认错题");
    const bare = await renderGrade(review([item(1)]));
    const bareButton = [...bare.querySelectorAll("button")].find((item) => item.textContent === "再出一份练习");
    expect(bareButton.disabled).toBe(true);
    expect(bare.textContent).toContain("暂无可再练的已确认错题");
  });

  it("shows a retired question as a Chinese refusal", async () => {
    const host = await renderGrade(mixed, async (path) => {
      if (String(path).endsWith("/follow-up")) {
        const error = new Error("retired");
        error.code = "retired";
        throw error;
      }
      return mixed;
    });
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "再出一份练习");
    await act(async () => {
      button.click();
    });
    expect(host.textContent).toContain("有题已经停用，不能再出练习");
  });
});

describe("teacher paper list", () => {
  it("names the source paper when this sheet is a follow-up", async () => {
    mockCall.mockImplementation(async (path) => {
      if (path === "/api/session") {
        return { student_ids: ["student-synth"], question_version_id: "q-synth", role: "teacher" };
      }
      if (path === "/api/catalog") {
        return { items: [{ question_version_id: "q-synth", stem: "synth-r8-stem" }] };
      }
      if (path === "/api/catalog/q-synth") {
        return {
          question_version_id: "q-synth",
          stem: "synth-r8-stem",
          answer_text: "synth-a",
          question_approved: false,
          answer_approved: false,
          retired: false,
        };
      }
      if (path === "/api/practice/papers") {
        return {
          papers: [
            {
              paper_id: "paper-synth-r8-new",
              student_id: "student-synth",
              status: "可打印",
              source_paper_id: "paper-synth-r8",
            },
            {
              paper_id: "paper-synth-r8",
              student_id: "student-synth",
              status: "已发放",
              source_paper_id: "",
            },
          ],
        };
      }
      if (String(path).endsWith("/intake")) return { pages: [] };
      return {};
    });
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        <MemoryRouter>
          <TeacherPage />
        </MemoryRouter>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    cleanup = () => {
      act(() => root.unmount());
      host.remove();
    };
    expect(host.textContent).toContain("再练自 paper-synth-r8");
    expect(host.textContent).not.toContain("再练自 paper-synth-r8-new");
  });
});
