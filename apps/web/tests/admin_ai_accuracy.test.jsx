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

function adminGets(path) {
  if (path === "/api/session") return jsonResponse(200, admin);
  if (path === "/api/account/sessions") return jsonResponse(200, { sessions: [] });
  if (path === "/api/admin/teachers") return jsonResponse(200, { teachers: [] });
  if (path === "/api/admin/students") return jsonResponse(200, { students: [] });
  if (path === "/api/admin/grants") return jsonResponse(200, { grants: [] });
  if (path === "/api/admin/audit") return jsonResponse(200, { events: [] });
  if (path === "/api/admin/errors") return jsonResponse(200, { errors: [] });
  return null;
}

function report(overrides) {
  return {
    current_threshold: 0.6,
    available_models: [
      { provider: "synth-prov", model: "synth-model-a" },
      { provider: "synth-prov", model: "synth-model-b" },
    ],
    runs: {
      total: 4,
      succeeded: 3,
      failed: 1,
      active: 0,
      failed_by_code: { timeout: 1 },
      external_match: { matched: 7, mismatched: 1, missing: 0 },
      page_match: { matched: 2, mismatched: 0, missing: 1 },
      input_tokens: 20,
      output_tokens: 8,
      ...((overrides && overrides.runs) || {}),
    },
    items: {
      decided_total: 9,
      linked_ai: 6,
      unlinked_manual: 3,
      by_source: { adopted: 4, revised: 1, manual: 1 },
      ai_decisive: 5,
      ai_unsure_or_unreadable: 1,
      agreed: 4,
      disagreed: 1,
      agreement_rate: 0.8,
      by_judged_by: {
        local: { total: 4, decisive: 3, agreed: 3, disagreed: 0, unsure_or_unreadable: 1, agreement_rate: 1 },
        model: { total: 2, decisive: 2, agreed: 1, disagreed: 1, unsure_or_unreadable: 0, agreement_rate: 0.5 },
      },
      ...((overrides && overrides.items) || {}),
    },
    thresholds: overrides && overrides.thresholds
      ? overrides.thresholds
      : [
          { threshold: 0.5, confident_count: 5, confident_agreed: 4, false_confident: 1, review_needed_count: 1, confident_accuracy: 0.8, coverage_rate: 0.8333 },
          { threshold: 0.6, confident_count: 4, confident_agreed: 3, false_confident: 1, review_needed_count: 2, confident_accuracy: 0.75, coverage_rate: 0.6667 },
          { threshold: 0.8, confident_count: 2, confident_agreed: 2, false_confident: 0, review_needed_count: 4, confident_accuracy: 1, coverage_rate: 0.3333 },
        ],
  };
}

describe("admin accuracy report", () => {
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

  it("shows an empty reconciliation", async () => {
    installFetch((path) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path.startsWith("/api/admin/ai/accuracy")) {
        return jsonResponse(200, {
          current_threshold: 0.6,
          available_models: [],
          runs: { total: 0, succeeded: 0, failed: 0, active: 0, failed_by_code: {}, external_match: { matched: 0, mismatched: 0, missing: 0 }, page_match: { matched: 0, mismatched: 0, missing: 0 }, input_tokens: 0, output_tokens: 0 },
          items: { decided_total: 0, linked_ai: 0, agreement_rate: null },
          thresholds: [],
        });
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("暂无已完成对账的 AI 识别记录"));
    expect(document.body.textContent).toContain("当前阈值 0.6");
  });

  it("shows counts and the threshold table", async () => {
    installFetch((path) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path.startsWith("/api/admin/ai/accuracy")) return jsonResponse(200, report());
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("学号匹配：一致 7"));
    expect(document.body.textContent).toContain("页码匹配：一致 2");
    expect(document.body.textContent).toContain("总体一致率 0.8");
    expect(document.body.textContent).toContain("本地判分");
    expect(document.body.textContent).toContain("模型判分");
    expect(document.body.textContent).toContain("输入 token 20");
    const row = [...document.querySelectorAll("tr")].find((item) => item.textContent.includes("0.6"));
    expect(row.textContent).toContain("1");
    expect(row.querySelector(".hint").textContent).toBe("1");
    expect(document.body.textContent).not.toContain("synth-transcribe-secret");
  });

  it("asks again when the model filter changes", async () => {
    installFetch((path) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path.startsWith("/api/admin/ai/accuracy")) {
        if (path.includes("model=synth-model-b")) {
          return jsonResponse(200, report({
            runs: { external_match: { matched: 1, mismatched: 0, missing: 4 } },
            thresholds: [
              { threshold: 0.6, confident_count: 1, confident_agreed: 1, false_confident: 0, review_needed_count: 1, confident_accuracy: 1, coverage_rate: 0.5 },
            ],
          }));
        }
        return jsonResponse(200, report());
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.querySelector("select[name=accuracy-model] option[value*='synth-model-b']"));
    const select = document.querySelector("select[name=accuracy-model]");
    const option = [...select.options].find((item) => item.textContent.includes("synth-model-b"));
    await act(async () => {
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await settle(() => document.body.textContent.includes("学号匹配：一致 1"));
    const filtered = fetch.mock.calls.map((call) => String(call[0])).filter((path) => path.includes("model=synth-model-b"));
    expect(filtered[0]).toContain("provider=synth-prov");
    expect(filtered[0]).toContain("model=synth-model-b");
    const row = [...document.querySelectorAll("tr")].find((item) => item.textContent.includes("0.6"));
    expect(row.querySelector(".hint").textContent).toBe("0");
  });

  it("shows the code, message, and request id when the report fails", async () => {
    installFetch((path) => {
      const listed = adminGets(path);
      if (listed) return listed;
      if (path.startsWith("/api/admin/ai/accuracy")) {
        return jsonResponse(403, { code: "permission_denied", message: "permission_denied", request_id: "req-accuracy" }, "req-accuracy");
      }
      return jsonResponse(404, { code: "not_found", message: "not_found", request_id: "req-missing" });
    });
    await renderAdmin();
    await settle(() => document.body.textContent.includes("req-accuracy"));
    expect(document.body.textContent).toContain("permission_denied：permission_denied");
    expect(button("刷新对账")).toBeTruthy();
  });
});
