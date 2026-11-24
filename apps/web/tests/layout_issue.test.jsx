import { describe, expect, it } from "vitest";
import { layoutIssueText } from "../src/paper_loop.js";

describe("layout issue text", () => {
  it("shows which question does not fit", () => {
    const text = layoutIssueText("item_too_long", "item_too_long：第 1 题放不下一整页（qv-synth-1）");
    expect(text).toContain("第 1 题");
    expect(text).toContain("qv-synth-1");
  });

  it("names the layout field", () => {
    const text = layoutIssueText("layout_invalid", "layout_invalid：qr_module 小于下限 1.7");
    expect(text).toContain("qr_module");
  });

  it("stays empty for other codes", () => {
    expect(layoutIssueText("not_approved", "not_approved：未核准")).toBe("");
  });
});
