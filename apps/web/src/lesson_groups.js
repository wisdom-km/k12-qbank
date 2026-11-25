export function issuableItem(row) {
  return Boolean(row && row.question_approved && row.answer_approved && !row.retired && !row.formula_note);
}

export function groupCatalog(items) {
  const books = [];
  const loose = [];
  const byBook = new Map();
  for (const row of items) {
    if (!row.book_id || !row.lesson_order) {
      loose.push(row);
      continue;
    }
    let book = byBook.get(row.book_id);
    if (!book) {
      book = { bookId: row.book_id, chapters: [] };
      byBook.set(row.book_id, book);
      books.push(book);
    }
    let chapter = book.chapters.find((item) => item.title === (row.chapter_title || ""));
    if (!chapter) {
      chapter = { title: row.chapter_title || "", sections: [] };
      book.chapters.push(chapter);
    }
    let section = chapter.sections.find((item) => item.title === (row.section_title || ""));
    if (!section) {
      section = { title: row.section_title || "", lessons: [] };
      chapter.sections.push(section);
    }
    let lesson = section.lessons.find((item) => item.order === row.lesson_order);
    if (!lesson) {
      lesson = { order: row.lesson_order, title: row.lesson_title || "", items: [] };
      section.lessons.push(lesson);
    }
    lesson.items.push(row);
  }
  return { books, loose };
}

export function lessonChoiceIds(rows) {
  return rows.filter(issuableItem).map((row) => row.question_version_id);
}
