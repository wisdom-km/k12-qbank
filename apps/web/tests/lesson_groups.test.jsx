import { expect, it } from "vitest";
import { groupCatalog, issuableItem, lessonChoiceIds } from "../src/lesson_groups.js";

it("groups a book lesson and leaves an old question loose", () => {
  const ready = {
    question_approved: true,
    answer_approved: true,
    retired: false,
  };
  const grouped = groupCatalog([
    {
      ...ready,
      question_version_id: "q-1",
      book_id: "synth-r4f",
      chapter_title: "synth-ch",
      section_title: "synth-sec",
      lesson_title: "synth-les",
      lesson_order: 1,
    },
    { ...ready, question_version_id: "q-2" },
    {
      ...ready,
      question_version_id: "q-3",
      book_id: "synth-r4f",
      chapter_title: "synth-ch",
      section_title: "synth-sec",
      lesson_order: 1,
      formula_note: "公式未结构化",
    },
  ]);
  expect(grouped.books).toHaveLength(1);
  expect(grouped.loose.map((row) => row.question_version_id)).toEqual(["q-2"]);
  const lesson = grouped.books[0].chapters[0].sections[0].lessons[0];
  expect(lesson.items.map((row) => row.question_version_id)).toEqual(["q-1", "q-3"]);
  expect(lessonChoiceIds(lesson.items)).toEqual(["q-1"]);
  expect(issuableItem(grouped.loose[0])).toBe(true);
});
