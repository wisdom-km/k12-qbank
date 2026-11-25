import { useEffect, useReducer, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { call } from "./auth.js";
import { attemptBlock, canHandOut, confirmReady, showConflictReload } from "./confirm_gate.js";
import { groupCatalog, lessonChoiceIds } from "./lesson_groups.js";
import { createPaperActions, layoutIssueText } from "./paper_loop.js";
import { IntakePanel } from "./intake_panel.jsx";
import { initialPaperState, paperReducer } from "./paper_state.js";

const REVIEW_VERSION_ID = "rev-1";

export function TeacherPage() {
  const [state, dispatch] = useReducer(paperReducer, initialPaperState);
  const stateRef = useRef(state);
  stateRef.current = state;
  const actions = useRef(null);
  if (actions.current === null) {
    const set = (key) => (value) => dispatch({ type: "set", key, value });
    actions.current = createPaperActions({
      call,
      reviewVersionId: REVIEW_VERSION_ID,
      get: () => stateRef.current,
      setSession: set("session"),
      setItems: set("items"),
      setChosen: set("chosen"),
      setItem: set("item"),
      setStudentId: set("studentId"),
      setPaper: set("paper"),
      setPapers: set("papers"),
      setAttempt: set("attempt"),
      setConfirmation: set("confirmation"),
      setSavedPayload: set("savedPayload"),
      setMessage: set("message"),
      setError: set("error"),
      setErrorCode: set("errorCode"),
      setIssuing: set("issuing"),
    });
  }
  const loop = actions.current;
  const set = (key) => (value) => dispatch({ type: "set", key, value });
  const setItem = set("item");
  const setStudentId = set("studentId");
  const setDecision = set("decision");
  const setOperationKey = set("operationKey");
  const setError = set("error");
  const setErrorCode = set("errorCode");
  const setMessage = set("message");

  useEffect(() => {
    loop.load().catch((reason) => setError(reason.message));
  }, [loop]);

  async function run(action) {
    setError("");
    setErrorCode("");
    setMessage("");
    try {
      await action();
    } catch (reason) {
      setErrorCode(reason.code || "");
      setError(reason.code ? reason.code + "：" + reason.message : reason.message);
    }
  }

  function publish() {
    return run(async () => {
      const next = await call("/api/catalog/" + state.item.question_version_id + "/publish", {
        method: "POST",
        body: "{}",
      });
      setItem(next);
      set("items")((rows) =>
        rows.map((row) =>
          row.question_version_id === next.question_version_id
            ? {
                ...row,
                stem: next.stem,
                answer_text: next.answer_text,
                question_approved: next.question_approved,
                answer_approved: next.answer_approved,
                retired: next.retired,
              }
            : row,
        ),
      );
      setMessage("已核准并发布");
    });
  }

  const [openLessons, setOpenLessons] = useState(() => new Set(["loose"]));
  const { session, items, chosen, item, studentId, paper, papers, attempt, decision, operationKey } = state;
  const { confirmation, savedPayload, message, error, errorCode, issuing } = state;
  const approved = Boolean(item && item.question_approved && item.answer_approved && !item.retired);
  const waitingReason = paper && paper.status === "待渲染" && (paper.render_code || paper.render_message);
  const blocked = attemptBlock(errorCode);
  const layoutNotice = layoutIssueText(errorCode, error);
  const grouped = groupCatalog(items);

  return (
    <main>
      <header>
        <h1>有理数出卷</h1>
        <Link to="/account">修改我的口令</Link>
      </header>
      <p className="note">逐题核验当前库里的题。勾选两道已核验的题会出在同一张卷上。只出一道时用当前选中的题。操作键由这次提交带上，谁生成这串文字还没定。</p>
      {session && <p className="note">当前老师：{session.actor_teacher_id}</p>}
      {error && <p className="error">{error}</p>}
      {message && <p className="ok">{message}</p>}

      <section>
        <h2>核验</h2>
        {items.length > 0 && (
          <div className="catalog-tree">
            {grouped.books.map((book) => (
              <section key={book.bookId} className="lesson-book">
                <h3>{book.bookId}</h3>
                {book.chapters.map((chapter) => (
                  <div key={book.bookId + chapter.title}>
                    {chapter.title && <h4>{chapter.title}</h4>}
                    {chapter.sections.map((section) => (
                      <div key={book.bookId + chapter.title + section.title}>
                        {section.title && <p className="note">{section.title}</p>}
                        {section.lessons.map((lesson) => {
                          const key = book.bookId + ":" + lesson.order;
                          return (
                            <LessonBlock
                              key={key}
                              title={"课时 " + lesson.order + " " + lesson.title}
                              count={lessonChoiceIds(lesson.items).length}
                              open={openLessons.has(key)}
                              onToggle={() => toggleLesson(setOpenLessons, key)}
                              onSelect={() => selectLesson(set, chosen, lesson.items)}
                              rows={lesson.items}
                              chosen={chosen}
                              onOpen={(id) => loop.selectQuestion(id)}
                              onToggleRow={(id) => toggleChosen(set, chosen, id)}
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                ))}
              </section>
            ))}
            {grouped.loose.length > 0 && (
              <LessonBlock
                title="未归类"
                count={lessonChoiceIds(grouped.loose).length}
                open={openLessons.has("loose")}
                onToggle={() => toggleLesson(setOpenLessons, "loose")}
                onSelect={() => selectLesson(set, chosen, grouped.loose)}
                rows={grouped.loose}
                chosen={chosen}
                onOpen={(id) => loop.selectQuestion(id)}
                onToggleRow={(id) => toggleChosen(set, chosen, id)}
              />
            )}
          </div>
        )}
        {item && (
          <>
            <dl>
              <dt>题干</dt>
              <dd className="formula">{item.stem}</dd>
              <dt>答案</dt>
              <dd className="formula">{item.answer_text}</dd>
              <dt>题目核验</dt>
              <dd>{item.question_approved ? "已核验" : "未核验"}</dd>
              <dt>答案核验</dt>
              <dd>{item.answer_approved ? "已核验" : "未核验"}</dd>
              <dt>停用</dt>
              <dd>{item.retired ? "已停用" : "未停用"}</dd>
            </dl>
            <button type="button" onClick={publish} disabled={approved || item.retired}>
              核准并发布
            </button>
          </>
        )}
      </section>

      <section>
        <h2>出卷</h2>
        <label>
          学生
          <select value={studentId} onChange={(event) => setStudentId(event.target.value)}>
            {(session ? session.student_ids : []).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => loop.issue()} disabled={!(approved || chosen.length >= 2)}>
          出卷
        </button>
        {layoutNotice && <p className="error">{layoutNotice}</p>}
        {paper && (
          <dl>
            <dt>卷号</dt>
            <dd>{paper.paper_id}</dd>
            <dt>状态</dt>
            <dd>{paper.status}</dd>
            <dt>学号</dt>
            <dd>{paper.student_id}</dd>
            <dt>文件</dt>
            <dd>{paper.file_id || "还没有"}</dd>
          </dl>
        )}
        {waitingReason && (
          <p className="error">
            {paper.render_code}：{paper.render_message}
          </p>
        )}
        {paper && paper.file_id && (
          <p>
            <a href={"/api/practice/files/" + paper.file_id} target="_blank" rel="noreferrer">
              打开 PDF
            </a>
          </p>
        )}
        {canHandOut(paper, issuing) && (
          <button type="button" onClick={() => loop.handOut()}>
            正式发放
          </button>
        )}
        {papers.length > 0 && (
          <ul>
            {papers.map((row) => (
              <li key={row.paper_id}>
                <button type="button" onClick={() => loop.choosePaper(row)}>
                  {row.student_id} · {row.status} · {row.paper_id}
                  {row.source_paper_id ? " · 再练自 " + row.source_paper_id : ""}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <IntakePanel papers={papers} call={call} />

      <section>
        <h2>确认</h2>
        {attempt && (
          <dl>
            <dt>合成作答</dt>
            <dd className="formula">{attempt.answer_text}</dd>
            <dt>作答编号</dt>
            <dd>{attempt.fixture_answer_id}</dd>
            <dt>小问</dt>
            <dd>{attempt.sub_question_id}</dd>
            <dt>复核</dt>
            <dd>{attempt.review_version_id}</dd>
          </dl>
        )}
        <label>
          决定
          <select value={decision} onChange={(event) => setDecision(event.target.value)}>
            <option value="adopt">采纳</option>
            <option value="revise">修改</option>
            <option value="reject">驳回</option>
          </select>
        </label>
        <label>
          操作键
          <input value={operationKey} onChange={(event) => setOperationKey(event.target.value)} />
        </label>
        {blocked && <p className="error">{blocked.notice}</p>}
        <button
          type="button"
          onClick={() => loop.confirm()}
          disabled={!confirmReady(paper, attempt) || Boolean(blocked) || issuing}
        >
          确认
        </button>
        <button type="button" onClick={() => loop.retry()} disabled={!savedPayload}>
          同键重试
        </button>
        {showConflictReload(errorCode) && paper && (
          <button type="button" onClick={() => loop.choosePaper(paper)}>
            重新查看当前作答
          </button>
        )}
        {blocked && paper && (
          <button type="button" onClick={() => loop.choosePaper(paper)}>
            {blocked.nextStep}
          </button>
        )}
        {confirmation && (
          <p className="ok">
            确认号 {confirmation.confirmation_id}，正式记录 {confirmation.count} 条
          </p>
        )}
      </section>
    </main>
  );
}

function LessonBlock({ title, count, open, onToggle, onSelect, rows, chosen, onOpen, onToggleRow }) {
  return (
    <div className="lesson-block">
      <div className="lesson-actions">
        <button type="button" onClick={onToggle}>
          {open ? "收起" : "展开"} {title}
        </button>
        <button type="button" onClick={onSelect}>
          选中本课时全部可出卷的题
        </button>
        <span>{count} 道可出卷</span>
      </div>
      {open && (
        <ul>
          {rows.map((row) => {
            const ready = row.question_approved && row.answer_approved && !row.retired;
            return (
              <li key={row.question_version_id}>
                <button type="button" onClick={() => onOpen(row.question_version_id)}>
                  {row.question_version_id} · {ready ? "已核验" : "未核验"}
                  {row.stem ? " · " + row.stem.slice(0, 24) : ""}
                </button>
                {ready && (
                  <label>
                    <input
                      type="checkbox"
                      checked={chosen.includes(row.question_version_id)}
                      onChange={() => onToggleRow(row.question_version_id)}
                    />
                    纳入本卷
                  </label>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function toggleLesson(setOpen, key) {
  setOpen((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  });
}

function selectLesson(set, chosen, rows) {
  const ids = lessonChoiceIds(rows);
  set("chosen")(Array.from(new Set(chosen.concat(ids))));
}

function toggleChosen(set, chosen, id) {
  set("chosen")(chosen.includes(id) ? chosen.filter((item) => item !== id) : chosen.concat(id));
}
