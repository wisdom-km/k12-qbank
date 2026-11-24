import { createRoot } from "react-dom/client";
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";
import jsQR from "jsqr";
import fixture from "./fixtures/qr_synth.json";
import { decodeQr } from "../src/intake_decode.js";
import { IntakePanel } from "../src/intake_panel.jsx";

const PAYLOAD = fixture.payload;

function raster(modules, moduleSize, quiet) {
  const count = modules.length;
  const span = count + quiet * 2;
  const width = span * moduleSize;
  const data = new Uint8ClampedArray(width * width * 4);
  for (let y = 0; y < width; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const col = Math.floor(x / moduleSize) - quiet;
      const row = Math.floor(y / moduleSize) - quiet;
      const dark = row >= 0 && col >= 0 && row < count && col < count && modules[row][col] === 1;
      const offset = (y * width + x) * 4;
      const value = dark ? 0 : 255;
      data[offset] = value;
      data[offset + 1] = value;
      data[offset + 2] = value;
      data[offset + 3] = 255;
    }
  }
  return { data, width };
}

function withNoise(data) {
  const copy = new Uint8ClampedArray(data);
  for (let index = 0; index < copy.length; index += 4) {
    const delta = (index / 4) % 5 - 2;
    copy[index] = clamp(copy[index] + delta);
    copy[index + 1] = clamp(copy[index + 1] + delta);
    copy[index + 2] = clamp(copy[index + 2] + delta);
  }
  return copy;
}

function clamp(value) {
  return Math.max(0, Math.min(255, value));
}

const papers = [
  {
    paper_id: "paper-synth-r5",
    printed_external_id: "synth-0001",
    issued_on: "2026-11-24",
    page_count: 2,
    student_id: "student-hidden-r5",
  },
];

let cleanup = () => {};

afterEach(() => {
  cleanup();
  cleanup = () => {};
});

async function renderPanel(shots, call) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<IntakePanel papers={papers} call={call} initialShots={shots} />);
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

describe("intake qr", () => {
  it("decodes a scaled synth matrix with a quiet zone", () => {
    const image = raster(fixture.modules, 4, 4);
    const hit = jsQR(image.data, image.width, image.width);
    expect(hit && hit.data).toBe(PAYLOAD);
    expect(decodeQr(image.data, image.width, image.width)).toBe(PAYLOAD);
  });

  it("decodes a smaller module size with a little noise", () => {
    const image = raster(fixture.modules, 2, 4);
    const noisy = withNoise(image.data);
    const hit = jsQR(noisy, image.width, image.width);
    expect(hit && hit.data).toBe(PAYLOAD);
  });
});

describe("intake panel", () => {
  it("shows 未识别 and the manual paper and page picks", async () => {
    const host = await renderPanel(
      [
        {
          id: "shot-unread",
          thumb: "",
          blob: null,
          payload: "",
          paperId: "",
          pageNo: 0,
          phase: "unread",
          note: "",
        },
      ],
      async (path) => {
        if (String(path).endsWith("/intake")) {
          return {
            paper_id: "paper-synth-r5",
            page_count: 2,
            pages: [
              { page_no: 1, received: false },
              { page_no: 2, received: true, located_by: "manual", uploaded_at: "2026-11-24T00:00:00Z", intake_id: "intake-synth" },
            ],
          };
        }
        return {};
      },
    );
    const text = host.textContent;
    expect(text).toContain("未识别");
    expect(text).toContain("选择卷");
    expect(text).toContain("选择页");
    expect(text).toContain("学号 synth-0001");
    expect(text).toContain("缺第 1 页");
    expect(text).not.toContain("student-hidden-r5");
  });

  it("shows the student number and page when the code matches an issued paper", async () => {
    const host = await renderPanel(
      [
        {
          id: "shot-read",
          thumb: "",
          blob: null,
          payload: "paper-synth-r5#1",
          paperId: "paper-synth-r5",
          pageNo: 1,
          phase: "done",
          note: "",
        },
      ],
      async () => ({ paper_id: "paper-synth-r5", page_count: 2, pages: [] }),
    );
    expect(host.textContent).toContain("学号 synth-0001，第 1 / 2 页");
    expect(host.textContent).not.toContain("student-hidden-r5");
  });

  it("asks 替换吗 when the page was already received", async () => {
    const host = await renderPanel(
      [
        {
          id: "shot-replace",
          thumb: "",
          blob: new Blob([Uint8Array.from([1, 2, 3])], { type: "image/jpeg" }),
          payload: "paper-synth-r5#1",
          paperId: "paper-synth-r5",
          pageNo: 1,
          phase: "ready",
          note: "",
        },
      ],
      (path, options) => {
        if (options && options.method === "PUT") {
          const error = new Error("page");
          error.code = "page_already_received";
          return Promise.reject(error);
        }
        return Promise.resolve({
          paper_id: "paper-synth-r5",
          page_count: 2,
          pages: [{ page_no: 1, received: true }, { page_no: 2, received: false }],
        });
      },
    );
    expect(host.textContent).toContain("替换吗");
    const button = [...host.querySelectorAll("button")].find((item) => item.textContent === "替换");
    expect(button).toBeTruthy();
    expect(host.textContent).not.toContain("student-hidden-r5");
  });
});
