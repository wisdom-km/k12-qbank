/** Read a book folder into the existing import request. The server decides outcomes. */

const KNOWN_MANIFEST = new Set([
  "book_id",
  "subject_id",
  "pairs",
  "answer_space",
  "question_dir",
  "answer_dir",
  "toc_dir",
  "toc_page_offset",
]);

const IGNORED_DIRS = new Set(["_review_backups", "_export_backups", "_import_reports"]);

const MANIFEST_MISSING = "import-book.json 无法读取，没有发送请求。请先在书目录根放好 import-book.json。";
const MANIFEST_SYNTAX = "import-book.json 语法不合法，没有发送请求。请先在书目录根放好 import-book.json。";

export async function filesFromDataTransfer(dataTransfer) {
  const items = dataTransfer && dataTransfer.items ? dataTransfer.items : [];
  const collected = [];
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    const entry = item && item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
    if (entry) {
      await walkEntry(entry, "", collected);
      continue;
    }
    if (item && item.kind === "file" && item.getAsFile) {
      const file = item.getAsFile();
      if (file) collected.push({ path: file.name, file });
    }
  }
  return collected;
}

export function filesFromInput(fileList) {
  const list = fileList || [];
  const collected = [];
  for (let index = 0; index < list.length; index += 1) {
    const file = list[index];
    collected.push({ path: file.webkitRelativePath || file.name, file });
  }
  return collected;
}

export async function packBook(entries) {
  const files = stripSharedRoot(entries || []);
  const manifestFile = files.find((item) => item.path === "import-book.json");
  if (!manifestFile) return { ok: false, message: MANIFEST_MISSING };
  let raw = "";
  try {
    raw = await readText(manifestFile);
  } catch (reason) {
    return { ok: false, message: MANIFEST_MISSING };
  }
  let manifest;
  try {
    manifest = JSON.parse(raw);
  } catch (reason) {
    return { ok: false, message: MANIFEST_SYNTAX };
  }
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    return { ok: false, message: MANIFEST_SYNTAX };
  }
  const questionDir = safeDir(manifest.question_dir, "question_dir");
  if (!questionDir.ok) return questionDir;
  const answerDir = safeDir(manifest.answer_dir, "answer_dir");
  if (!answerDir.ok) return answerDir;
  const tocDir = safeDir(manifest.toc_dir, "toc_dir");
  if (!tocDir.ok) return tocDir;

  const split = questionDir.dir !== null || answerDir.dir !== null;
  let pages = [];
  if (!split) {
    const read = await readPages(files, null, "");
    if (!read.ok) return read;
    pages = read.pages;
  } else {
    const questions = await readPages(files, questionDir.dir, "questions");
    if (!questions.ok) return questions;
    pages = questions.pages;
    if (answerDir.dir !== null) {
      const answers = await readPages(files, answerDir.dir, "answers");
      if (!answers.ok) return answers;
      pages = pages.concat(answers.pages);
    }
  }
  pages.sort((left, right) => left.pdf_page - right.pdf_page || compareText(left.role, right.role));

  let toc = [];
  if (tocDir.dir !== null) {
    const read = await readToc(files, tocDir.dir);
    if (!read.ok) return read;
    toc = read.toc;
  }

  const bookId = typeof manifest.book_id === "string" ? manifest.book_id : "";
  const body = {
    subject_id: Object.prototype.hasOwnProperty.call(manifest, "subject_id") ? manifest.subject_id : "",
    dry_run: false,
    pages,
    pairing: Object.prototype.hasOwnProperty.call(manifest, "pairs") ? manifest.pairs : [],
    answer_space: Object.prototype.hasOwnProperty.call(manifest, "answer_space") ? manifest.answer_space : [],
  };
  if (toc.length) body.toc = toc;
  if (Object.prototype.hasOwnProperty.call(manifest, "toc_page_offset")) {
    body.toc_page_offset = manifest.toc_page_offset;
  }
  for (const key of Object.keys(manifest)) {
    if (!KNOWN_MANIFEST.has(key)) body[key] = manifest[key];
  }
  return {
    ok: true,
    bookId,
    summary: {
      book_id: bookId,
      subject_id: body.subject_id,
      question_pages: pages.filter((page) => page.role === "questions").length,
      answer_pages: pages.filter((page) => page.role === "answers").length,
      toc_pages: toc.length,
    },
    body,
  };
}

async function walkEntry(entry, prefix, out) {
  const path = prefix + entry.name;
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => {
      entry.file(resolve, reject);
    });
    out.push({ path, file });
    return;
  }
  if (!entry.isDirectory || !entry.createReader) return;
  const reader = entry.createReader();
  const children = [];
  while (true) {
    const batch = await new Promise((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (!batch || batch.length === 0) break;
    for (let index = 0; index < batch.length; index += 1) children.push(batch[index]);
  }
  for (const child of children) await walkEntry(child, path + "/", out);
}

function stripSharedRoot(entries) {
  const normalized = [];
  for (const entry of entries) {
    const path = cleanPath(entry && entry.path);
    if (!path) continue;
    normalized.push({ ...entry, path });
  }
  if (!normalized.length) return normalized;
  const first = normalized[0].path.split("/")[0];
  const nested = normalized.every((entry) => entry.path.includes("/"));
  const shared = normalized.every((entry) => entry.path.split("/")[0] === first);
  const rooted = normalized.some((entry) => entry.path === "import-book.json");
  if (!nested || !shared || rooted) return normalized;
  const prefix = first + "/";
  return normalized.map((entry) => ({ ...entry, path: entry.path.slice(prefix.length) }));
}

function cleanPath(raw) {
  return String(raw || "")
    .replace(/\\/g, "/")
    .split("/")
    .filter((part) => part !== "" && part !== ".")
    .join("/");
}

function safeDir(raw, label) {
  if (raw === undefined || raw === null || raw === "") return { ok: true, dir: null };
  if (typeof raw !== "string") {
    return { ok: false, message: label + " 必须是相对路径，没有发送请求。" };
  }
  const slash = raw.replace(/\\/g, "/");
  if (slash.startsWith("/") || slash.startsWith("//") || /^[A-Za-z]:/.test(slash)) {
    return { ok: false, message: label + " 必须是相对路径，不能是绝对路径。没有发送请求。" };
  }
  const parts = slash.split("/").filter((part) => part !== "" && part !== ".");
  if (parts.some((part) => part === "..")) {
    return { ok: false, message: label + " 不能含 ..。没有发送请求。" };
  }
  return { ok: true, dir: parts.join("/") };
}

async function readPages(files, dir, volume) {
  const grouped = new Map();
  const sorted = filesUnder(files, dir).sort((left, right) => compareText(left.relative, right.relative));
  for (const item of sorted) {
    if (ignored(item.relative)) continue;
    const stem = stemOf(item.relative);
    if (stem === null) continue;
    const slot = grouped.get(stem) || { roleText: null, questions: null, answers: [] };
    const name = fileName(item.relative);
    if (name.endsWith(".page-role.txt")) slot.roleText = item;
    else if (name.endsWith(".questions.json")) slot.questions = item;
    else if (parentName(item.relative).endsWith(".answers") && name.endsWith(".json")) slot.answers.push(item);
    grouped.set(stem, slot);
  }
  const pages = [];
  for (const [stem, slot] of grouped) {
    const number = pageNumber(stem);
    if (number === null) continue;
    let roleText = null;
    if (slot.roleText) {
      try {
        roleText = await readText(slot.roleText.entry);
      } catch (reason) {
        return { ok: false, message: slot.roleText.entry.path + " 无法读取，没有发送请求。" };
      }
    }
    let role = roleOf(roleText);
    if (volume === "answers") role = "answers";
    else if (volume === "questions") role = "questions";
    if (role === "questions") {
      if (!slot.questions) continue;
      const payload = await readJson(slot.questions);
      if (!payload.ok) return payload;
      const page = { pdf_page: number, role: "questions", questions: payload.value, answers: [] };
      if (volume) page.volume = volume;
      pages.push(page);
      continue;
    }
    const hasQuestions = Boolean(slot.questions);
    if (!slot.answers.length) {
      if (volume === "answers" && hasQuestions) {
        pages.push({
          pdf_page: number,
          role: "answers",
          volume: "answers",
          questions: null,
          answers: [],
          has_question_file: true,
        });
      }
      continue;
    }
    const answers = [];
    const ordered = [...slot.answers].sort((left, right) => compareText(fileName(left.relative), fileName(right.relative)));
    for (const item of ordered) {
      const payload = await readJson(item);
      if (!payload.ok) return payload;
      answers.push(payload.value);
    }
    const page = { pdf_page: number, role: "answers", questions: null, answers };
    if (volume) page.volume = volume;
    pages.push(page);
  }
  return { ok: true, pages };
}

async function readToc(files, dir) {
  const rows = [];
  for (const item of filesUnder(files, dir)) {
    if (ignored(item.relative) || !item.relative.toLowerCase().endsWith(".md")) continue;
    const number = pageNumber(item.relative);
    if (number === null) continue;
    let text = "";
    try {
      text = await readText(item.entry);
    } catch (reason) {
      return { ok: false, message: item.entry.path + " 无法读取，没有发送请求。" };
    }
    rows.push({ pdf_page: number, text });
  }
  rows.sort((left, right) => left.pdf_page - right.pdf_page);
  return { ok: true, toc: rows };
}

function filesUnder(files, dir) {
  const found = [];
  for (const entry of files) {
    const relative = relativeTo(dir, entry.path);
    if (relative === null || relative === "") continue;
    found.push({ entry, relative });
  }
  return found;
}

function relativeTo(dir, path) {
  if (dir === null || dir === "") return path;
  if (path === dir) return "";
  const prefix = dir + "/";
  if (path.startsWith(prefix)) return path.slice(prefix.length);
  return null;
}

function ignored(relative) {
  const parts = relative.split("/");
  const name = parts[parts.length - 1];
  if (parts.some((part) => part.startsWith(".") || IGNORED_DIRS.has(part))) return true;
  if (name.includes(".reviewed.") || name.endsWith(".reviewed")) return true;
  return name.endsWith(".answers-meta.json");
}

function stemOf(relative) {
  if (pageNumber(relative) === null) return null;
  const name = fileName(relative);
  const parent = parentPath(relative);
  if (name.endsWith(".questions.json")) return joinPath(parent, name.slice(0, -".questions.json".length));
  if (name.endsWith(".page-role.txt")) return joinPath(parent, name.slice(0, -".page-role.txt".length));
  const folder = parentName(relative);
  if (folder.endsWith(".answers") && name.endsWith(".json")) {
    return joinPath(parentPath(parent), folder.slice(0, -".answers".length));
  }
  return null;
}

function pageNumber(value) {
  const found = String(value).match(/page_(\d+)/gi);
  if (!found || !found.length) return null;
  const digits = found[found.length - 1].match(/(\d+)/);
  return digits ? Number(digits[1]) : null;
}

function roleOf(raw) {
  if (typeof raw !== "string") return "questions";
  return raw.trim() === "answers" ? "answers" : "questions";
}

async function readJson(item) {
  let raw = "";
  try {
    raw = await readText(item.entry);
  } catch (reason) {
    return { ok: false, message: item.entry.path + " 无法读取，没有发送请求。" };
  }
  try {
    return { ok: true, value: JSON.parse(raw) };
  } catch (reason) {
    return { ok: false, message: item.entry.path + " 无法读取，没有发送请求。" };
  }
}

async function readText(entry) {
  if (typeof entry.text === "string") return entry.text;
  const source = entry.file && typeof entry.file.text === "function" ? entry.file : entry;
  if (typeof source.text === "function") return source.text();
  throw new Error("read");
}

function fileName(path) {
  const parts = String(path).split("/");
  return parts[parts.length - 1] || "";
}

function parentPath(path) {
  const parts = String(path).split("/");
  parts.pop();
  return parts.join("/");
}

function parentName(path) {
  return fileName(parentPath(path));
}

function joinPath(parent, name) {
  return parent ? parent + "/" + name : name;
}

function compareText(left, right) {
  const a = String(left);
  const b = String(right);
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
