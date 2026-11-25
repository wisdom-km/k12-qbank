import { useEffect, useRef, useState } from "react";
import { callWithId } from "./auth.js";
import { filesFromDataTransfer, filesFromInput, packBook } from "./book_import_pack.js";

export function importPreviewClean(report) {
  if (!report || typeof report !== "object") return false;
  if (report.reason) return false;
  if (report.conflict !== 0) return false;
  if (!Array.isArray(report.pages)) return false;
  return report.pages.every((page) => page && page.outcome === "ok");
}

export function BookImportPanel({ onImported }) {
  const inputRef = useRef(null);
  const generation = useRef(0);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState("");
  const [pack, setPack] = useState(null);
  const [report, setReport] = useState(null);
  const [readError, setReadError] = useState("");
  const [httpError, setHttpError] = useState(null);

  useEffect(() => {
    const node = inputRef.current;
    if (!node) return;
    node.setAttribute("webkitdirectory", "");
    node.setAttribute("directory", "");
    node.multiple = true;
  }, []);

  async function loadEntries(entries) {
    const ticket = generation.current + 1;
    generation.current = ticket;
    setPack(null);
    setReport(null);
    setReadError("");
    setHttpError(null);
    setBusy("");
    if (!entries || !entries.length) {
      setReadError("没有读到书目录。");
      return;
    }
    let result;
    try {
      result = await packBook(entries);
    } catch (reason) {
      if (generation.current !== ticket) return;
      setReadError("书目录无法读取，没有发送请求。");
      return;
    }
    if (generation.current !== ticket) return;
    if (!result.ok) {
      setReadError(result.message);
      return;
    }
    setPack({ ...result, generation: ticket });
  }

  function onPick(event) {
    const picked = filesFromInput(event.target.files);
    event.target.value = "";
    void loadEntries(picked);
  }

  async function onDrop(event) {
    event.preventDefault();
    setOver(false);
    const entries = await filesFromDataTransfer(event.dataTransfer);
    void loadEntries(entries);
  }

  async function runPreview() {
    await submit(true);
  }

  async function runWrite() {
    await submit(false);
  }

  async function submit(dryRun) {
    if (!pack || busy) return;
    if (!pack.bookId) {
      setReadError("import-book.json 缺少 book_id，没有发送请求。");
      setReport(null);
      return;
    }
    if (!dryRun && !(report && report.generation === pack.generation && importPreviewClean(report.data))) return;
    const ticket = generation.current;
    setBusy(dryRun ? "preview" : "write");
    setHttpError(null);
    setReadError("");
    try {
      const result = await callWithId("/api/admin/catalog/books/" + encodeURIComponent(pack.bookId) + "/import", {
        method: "POST",
        body: JSON.stringify({ ...pack.body, dry_run: dryRun }),
      });
      if (generation.current !== ticket) return;
      setReport({ generation: ticket, data: result.body || {}, requestId: result.requestId || "" });
      if (!dryRun && result.body && result.body.written && onImported) await onImported();
    } catch (reason) {
      if (generation.current !== ticket) return;
      if (dryRun) setReport(null);
      setHttpError({
        code: (reason && reason.code) || "",
        message: (reason && reason.message) || "",
        request_id: (reason && reason.request_id) || "",
      });
    } finally {
      if (generation.current === ticket) setBusy("");
    }
  }

  const summary = pack && pack.summary;
  const data = report && report.data;
  const canWrite = Boolean(pack && report && report.generation === pack.generation && importPreviewClean(data) && !busy);
  const showToc = Boolean(data && (tocVisible(data) || (summary && summary.toc_pages > 0)));

  return (
    <section className="book-import">
      <h2>整书导入</h2>
      <p className="note">把书文件夹拖进来，或选择文件夹。先预演，预演没有拦截再确认写入。规则在服务端。</p>
      <div
        className={over ? "book-drop over" : "book-drop"}
        onDragEnter={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setOver(false);
        }}
        onDrop={onDrop}
      >
        <p>把书文件夹拖到这里</p>
        <button type="button" onClick={() => inputRef.current && inputRef.current.click()}>
          选择书文件夹
        </button>
        <input ref={inputRef} className="book-file-input" type="file" multiple onChange={onPick} />
      </div>
      {readError && <p className="error">{readError}</p>}
      {summary && (
        <dl className="book-summary">
          <dt>book_id</dt>
          <dd>{summary.book_id || "（空）"}</dd>
          <dt>subject_id</dt>
          <dd>{typeof summary.subject_id === "string" ? summary.subject_id : ""}</dd>
          <dt>题目页</dt>
          <dd>{summary.question_pages}</dd>
          <dt>答案页</dt>
          <dd>{summary.answer_pages}</dd>
          <dt>目录页</dt>
          <dd>{summary.toc_pages}</dd>
        </dl>
      )}
      <button type="button" disabled={!pack || busy !== ""} onClick={runPreview}>
        {busy === "preview" ? "正在预演…" : "预演导入"}
      </button>
      <button type="button" disabled={!canWrite} onClick={runWrite}>
        {busy === "write" ? "正在写入…" : "确认写入"}
      </button>
      {httpError && (
        <p className="error">
          {httpError.code}：{httpError.message} {httpError.request_id}
        </p>
      )}
      {data && (
        <div className="book-report">
          <p>
            request_id {report.requestId} · <span className="book-status">{statusLabel(data)}</span>
            {data.reason ? " · " + data.reason : ""}
          </p>
          <p>
            staged {countOf(data, "staged")} · kept {countOf(data, "kept")} · skipped {countOf(data, "skipped")} · conflict {countOf(data, "conflict")} · space_changed {countOf(data, "space_changed")}
          </p>
          {showToc && (
            <div>
              <p>
                章 {countOf(data, "toc_chapters")} · 节 {countOf(data, "toc_sections")} · 课时 {countOf(data, "toc_lessons")} · toc_changed {data.toc_changed ? "是" : "否"}
              </p>
              <ul>
                {unparsedRows(data).map((row) => (
                  <li key={String(row.pdf_page) + ":" + String(row.line)}>
                    pdf_page {row.pdf_page} · line {row.line}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="report-scroll">
            <table>
              <thead>
                <tr>
                  <th>volume</th>
                  <th>pdf_page</th>
                  <th>role</th>
                  <th>outcome</th>
                  <th>reason</th>
                  <th>hint</th>
                </tr>
              </thead>
              <tbody>
                {(data.pages || []).map((page, index) => (
                  <tr key={String(page.volume || "") + ":" + String(page.pdf_page) + ":" + String(page.role) + ":" + index}>
                    <td>{page.volume || ""}</td>
                    <td>{page.pdf_page}</td>
                    <td>{page.role}</td>
                    <td>{page.outcome}</td>
                    <td>{page.reason || ""}</td>
                    <td className={page.hint ? "hint" : ""}>{page.hint || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="report-scroll">
            <table>
              <thead>
                <tr>
                  <th>original_key</th>
                  <th>question_version_id</th>
                  <th>outcome</th>
                  <th>reason</th>
                  <th>lesson_order</th>
                </tr>
              </thead>
              <tbody>
                {(data.questions || []).map((row, index) => (
                  <tr key={String(row.original_key) + ":" + index}>
                    <td>{row.original_key}</td>
                    <td>{row.question_version_id}</td>
                    <td>{row.outcome}</td>
                    <td>{row.reason || ""}</td>
                    <td>{row.lesson_order == null ? "" : row.lesson_order}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

function statusLabel(report) {
  if (!importPreviewClean(report)) return "已拒绝";
  if (report.dry_run) return "预演未写入";
  return "已写入";
}

function tocVisible(report) {
  return Boolean(
    countOf(report, "toc_chapters") ||
      countOf(report, "toc_sections") ||
      countOf(report, "toc_lessons") ||
      report.toc_changed ||
      (Array.isArray(report.toc_unparsed) && report.toc_unparsed.length),
  );
}

function unparsedRows(report) {
  if (!Array.isArray(report.toc_unparsed)) return [];
  return report.toc_unparsed.map((row) => ({
    pdf_page: row && row.pdf_page,
    line: row && row.line,
  }));
}

function countOf(report, key) {
  const value = report[key];
  return typeof value === "number" ? value : 0;
}
