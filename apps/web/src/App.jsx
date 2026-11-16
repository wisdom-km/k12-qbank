import { useEffect, useRef, useState } from "react";
import { call } from "./api.js";
import { attemptBlock, canHandOut, confirmReady, showConflictReload } from "./confirm_gate.js";
import { createPaperActions } from "./paper_loop.js";

const REVIEW_VERSION_ID = "rev-1";

export default function App() {
  const [session, setSession] = useState(null);
  const [item, setItem] = useState(null);
  const [studentId, setStudentId] = useState("student-synth");
  const [paper, setPaper] = useState(null);
  const [papers, setPapers] = useState([]);
  const [attempt, setAttempt] = useState(null);
  const [decision, setDecision] = useState("adopt");
  const [operationKey, setOperationKey] = useState("key-web-1");
  const [confirmation, setConfirmation] = useState(null);
  const [savedPayload, setSavedPayload] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [errorCode, setErrorCode] = useState("");
  const [issuing, setIssuing] = useState(false);
  const live = useRef({});
  live.current = {
    session,
    item,
    studentId,
    paper,
    attempt,
    confirmation,
    savedPayload,
    message,
    error,
    errorCode,
    decision,
    operationKey,
  };
  const actions = useRef(null);
  if (actions.current === null) {
    actions.current = createPaperActions({
      call,
      reviewVersionId: REVIEW_VERSION_ID,
      get: () => live.current,
      setSession,
      setItem,
      setStudentId,
      setPaper,
      setPapers,
      setAttempt,
      setConfirmation,
      setSavedPayload,
      setMessage,
      setError,
      setErrorCode,
      setIssuing,
    });
  }
  const loop = actions.current;

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
      const next = await call("/api/catalog/" + item.question_version_id + "/publish", {
        method: "POST",
        body: "{}",
      });
      setItem(next);
      setMessage("已核准并发布");
    });
  }

  const approved = Boolean(item && item.question_approved && item.answer_approved && !item.retired);
  const waitingReason = paper && paper.status === "待渲染" && (paper.render_code || paper.render_message);
  const blocked = attemptBlock(errorCode);

  return (
    <main>
      <h1>有理数出卷</h1>
      <p className="note">合成题和合成学生。操作键由这次提交带上，谁生成这串文字还没定。</p>
      {session && <p className="note">当前老师：{session.actor_teacher_id}</p>}
      {error && <p className="error">{error}</p>}
      {message && <p className="ok">{message}</p>}

      <section>
        <h2>核验</h2>
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
          合成学生
          <select value={studentId} onChange={(event) => setStudentId(event.target.value)}>
            {(session ? session.student_ids : []).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => loop.issue()} disabled={!approved}>
          出卷
        </button>
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
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

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
