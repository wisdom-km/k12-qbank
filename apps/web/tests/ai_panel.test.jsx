import { createRoot } from "react-dom/client";
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { AiPanel } from "../src/ai_panel.jsx";

const DISCLAIMER = "AI 建议，老师确认前不算结果";
const BANNER = "照片上的学号或页码和这张卷对不上，请核对";

let cleanup = () => {};

afterEach(() => {
  cleanup();
  cleanup = () => {};
  sessionStorage.clear();
});

async function renderPanel(run, call) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<AiPanel intakeId="intake-r6" call={call} initialRun={run} />);
  });
  cleanup = () => {
    act(() => root.unmount());
    host.remove();
  };
  return host;
}

describe("ai panel", () => {
  it("shows 识别中 while a run is open", async () => {
    const host = await renderPanel(
      { run_id: "run-open", status: "running", suggestions: [] },
      async () => ({ run_id: "run-open", status: "running", suggestions: [] }),
    );
    expect(host.textContent).toContain("识别中");
    expect(host.textContent).toContain(DISCLAIMER);
    expect(host.querySelector("button").disabled).toBe(true);
  });

  it("lists a finished suggestion", async () => {
    const host = await renderPanel(
      {
        run_id: "run-done",
        status: "succeeded",
        external_match: "unread",
        page_match: "consistent",
        suggestions: [
          {
            order_no: 1,
            transcription: "A",
            unreadable: false,
            confidence: 0.91,
            verdict: "correct",
            reason: "与标准答案一致",
            judged_by: "local",
          },
          {
            order_no: 2,
            transcription: "2",
            unreadable: false,
            confidence: 0.91,
            verdict: "partial",
            reason: "步骤对了",
            judged_by: "model",
          },
        ],
      },
      async () => ({}),
    );
    const text = host.textContent;
    expect(text).toContain("完成");
    expect(text).toContain(DISCLAIMER);
    expect(text).toContain("转写 A");
    expect(text).toContain("建议 对");
    expect(text).toContain("本机判");
    expect(text).toContain("建议 部分对");
    expect(text).toContain("模型判");
    expect(text).not.toContain("需要老师看");
    expect(text).not.toContain(BANNER);
  });

  it("offers 重试 after a failed run", async () => {
    const posts = [];
    const host = await renderPanel(
      { run_id: "run-fail", status: "failed", error_code: "timeout", suggestions: [] },
      (url, options) => {
        if (options && options.method === "POST") {
          posts.push({ url, body: options.body });
          return Promise.resolve({ run_id: "run-again", status: "queued" });
        }
        return Promise.resolve({});
      },
    );
    expect(host.textContent).toContain("失败");
    expect(host.textContent).toContain("超时");
    expect(host.textContent).toContain(DISCLAIMER);
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "重试");
    expect(button).toBeTruthy();
    await act(async () => {
      button.click();
    });
    expect(posts).toEqual([{ url: "/api/practice/intake/intake-r6/ai-runs", body: "{}" }]);
  });

  it("marks a low confidence or unreadable item for the teacher", async () => {
    const host = await renderPanel(
      {
        run_id: "run-look",
        status: "succeeded",
        suggestions: [
          {
            order_no: 1,
            transcription: "",
            unreadable: true,
            confidence: 0.9,
            verdict: "unsure",
            reason: "看不清",
            judged_by: "local",
          },
          {
            order_no: 2,
            transcription: "2",
            unreadable: false,
            confidence: 0.4,
            verdict: "incorrect",
            reason: "与标准答案不一致",
            judged_by: "model",
          },
        ],
      },
      async () => ({}),
    );
    const items = [...host.querySelectorAll("li")].map((item) => item.textContent);
    expect(items).toHaveLength(2);
    expect(items[0]).toContain("需要老师看");
    expect(items[1]).toContain("需要老师看");
    expect(host.textContent).toContain(DISCLAIMER);
  });

  it("warns when the printed number or page does not match", async () => {
    const host = await renderPanel(
      {
        run_id: "run-mismatch",
        status: "succeeded",
        external_match: "mismatch",
        page_match: "consistent",
        suggestions: [],
      },
      async () => ({}),
    );
    expect(host.textContent).toContain(BANNER);
    expect(host.textContent).toContain(DISCLAIMER);
    expect(host.textContent).not.toContain("synth-");
  });
});
