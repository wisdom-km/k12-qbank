import { createRoot } from "react-dom/client";
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { GradePage } from "../src/grade_page.jsx";

const DISCLAIMER = "AI 建议只有经老师采用或改判后才算结果";
const BANNER = "照片上的学号或页码和这张卷对不上，请核对";
const HIDDEN = "student-hidden-r7";

let cleanup = () => {};

afterEach(() => {
  cleanup();
  cleanup = () => {};
});

function suggestion(extra) {
  return {
    run_id: "run-r7",
    transcription: "2",
    confidence: 0.91,
    verdict: "correct",
    reason: "与标准答案一致",
    judged_by: "local",
    unreadable: false,
    needs_review: false,
    ...extra,
  };
}

function item(orderNo, extra) {
  return {
    order_no: orderNo,
    question_type: "solution",
    stem: "计算：(-3)+5",
    standard_answer: "2",
    page_no: 1,
    intake_status: "received",
    stale: false,
    suggestion: suggestion(),
    decision: null,
    ...extra,
  };
}

function review(items, extra) {
  return {
    paper_id: "paper-synth-r7",
    student_id: HIDDEN,
    threshold: 0.6,
    confirmed: 0,
    total: items.length,
    correct: 0,
    done: false,
    mismatch_pages: [],
    items,
    ...extra,
  };
}

async function renderGrade(body, call) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const request = call || (async () => body);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <GradePage paperId="paper-synth-r7" call={request} />
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

function setControl(element, value) {
  const prototype = Object.getPrototypeOf(element);
  const setter = Object.getOwnPropertyDescriptor(prototype, "value").set;
  setter.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("grade page", () => {
  it("ranks items that need a teacher first", async () => {
    const host = await renderGrade(
      review([
        item(1, { suggestion: suggestion({ confidence: 0.2, needs_review: true }) }),
        item(2, { suggestion: suggestion({ confidence: 0.91, judged_by: "model" }) }),
        item(3, {
          suggestion: suggestion({
            verdict: "unsure",
            confidence: 0.95,
            unreadable: true,
            needs_review: true,
            transcription: "",
          }),
        }),
      ]),
    );
    const rows = [...host.querySelectorAll("ol li")];
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("题 1"),
      expect.stringContaining("题 3"),
      expect.stringContaining("题 2"),
    ]);
    expect(rows[0].className).toContain("needs-review");
    expect(rows[1].className).toContain("needs-review");
    expect(rows[2].className).not.toContain("needs-review");
    expect(rows[0].textContent).toContain("需要老师看");
    expect(rows[2].textContent).toContain("模型判");
    expect(rows[2].textContent).not.toContain("需要老师看");
    const unsure = [...rows[1].querySelectorAll("button")].find((button) => button.textContent === "采用");
    expect(unsure.disabled).toBe(true);
    expect(host.textContent).toContain(DISCLAIMER);
    expect(host.textContent).not.toContain(HIDDEN);
  });

  it("adopts a suggestion", async () => {
    const calls = [];
    const first = review([item(1)]);
    const second = review([item(1, { decision: { verdict: "correct", source: "adopted", comment: "" } })], {
      confirmed: 1,
      correct: 1,
    });
    let reads = 0;
    const host = await renderGrade(first, async (url, options) => {
      calls.push({ url: String(url), method: options && options.method, body: options && options.body });
      if (options && options.method === "PUT") return {};
      reads += 1;
      return reads > 1 ? second : first;
    });
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "采用");
    await act(async () => {
      button.click();
    });
    expect(calls.some((call) => call.method === "PUT" && call.body === JSON.stringify({ action: "adopt" }))).toBe(true);
    expect(host.textContent).toContain("老师结论 对");
    expect(host.textContent).not.toContain(HIDDEN);
  });

  it("revises a suggestion", async () => {
    const calls = [];
    const host = await renderGrade(review([item(1)]), async (url, options) => {
      calls.push({ url: String(url), body: options && options.body });
      return review([item(1)]);
    });
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "改判");
    await act(async () => {
      button.click();
    });
    const verdict = host.querySelector('[aria-label="结论"]');
    const transcript = host.querySelector('[aria-label="修正转写"]');
    const comment = host.querySelector('[aria-label="评语"]');
    await act(async () => {
      setControl(verdict, "incorrect");
      setControl(transcript, "5");
      setControl(comment, "符号看错");
    });
    const save = [...host.querySelectorAll("button")].find((item) => item.textContent === "保存改判");
    await act(async () => {
      save.click();
    });
    const sent = calls.map((call) => call.body).find((body) => body && body.includes("revise"));
    expect(JSON.parse(sent)).toEqual({
      action: "revise",
      verdict: "incorrect",
      corrected_transcription: "5",
      comment: "符号看错",
    });
  });

  it("grades by hand when there is no suggestion", async () => {
    const calls = [];
    const host = await renderGrade(
      review([item(1, { suggestion: null, intake_status: "missing" })]),
      async (url, options) => {
        calls.push(options && options.body);
        return review([item(1, { suggestion: null })]);
      },
    );
    expect(host.textContent).toContain("没有 AI 建议");
    expect([...host.querySelectorAll("button")].some((button) => button.textContent === "采用")).toBe(false);
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "手评");
    await act(async () => {
      button.click();
    });
    const save = [...host.querySelectorAll("button")].find((item) => item.textContent === "保存手评");
    await act(async () => {
      save.click();
    });
    const sent = calls.find((body) => body && body.includes("manual"));
    expect(JSON.parse(sent).action).toBe("manual");
    expect(JSON.parse(sent).verdict).toBe("correct");
  });

  it("lists the confident items before adopting them", async () => {
    const calls = [];
    const body = review([
      item(1, { suggestion: suggestion({ confidence: 0.9 }) }),
      item(2, { suggestion: suggestion({ judged_by: "model", confidence: 0.99 }) }),
      item(3, { suggestion: suggestion({ confidence: 0.6, verdict: "incorrect" }) }),
      item(4, { suggestion: suggestion({ confidence: 0.4 }) }),
      item(5, { suggestion: suggestion({ verdict: "unsure", confidence: 0.9 }) }),
    ]);
    const host = await renderGrade(body, async (url, options) => {
      calls.push({ url: String(url), method: options && options.method, body: options && options.body });
      return body;
    });
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "采用全部高把握的本机判结果");
    await act(async () => {
      button.click();
    });
    const dialog = host.querySelector('[role="dialog"]');
    expect(dialog.getAttribute("aria-label")).toBe("确认采用");
    expect(dialog.textContent).toContain("将采用第 1、3 题");
    const confirm = [...dialog.querySelectorAll("button")].find((item) => item.textContent === "确认采用");
    await act(async () => {
      confirm.click();
    });
    expect(calls.some((call) => call.method === "POST" && String(call.url).endsWith("/decisions/adopt-confident"))).toBe(
      true,
    );
  });

  it("shows 已批完 when every item is confirmed", async () => {
    const host = await renderGrade(
      review(
        [item(1, { decision: { verdict: "correct", source: "adopted", comment: "" } })],
        { confirmed: 1, total: 1, correct: 1, done: true },
      ),
    );
    expect(host.textContent).toContain("已确认 1 / 共 1，对 1 题");
    expect(host.textContent).toContain("已批完");
    expect(host.textContent).toContain(DISCLAIMER);
  });

  it("shows the mismatch banner and a relocate control", async () => {
    const host = await renderGrade(review([item(1)], { mismatch_pages: [1] }));
    expect(host.textContent).toContain(BANNER);
    expect(host.textContent).toContain("重新定位这张照片");
    expect(host.querySelector('input[aria-label="重新定位这张照片"]')).toBeTruthy();
    expect(host.textContent).not.toContain(HIDDEN);
  });
});
