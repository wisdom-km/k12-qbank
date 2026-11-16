import { useEffect, useState } from "react";
import { call } from "./api.js";

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
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const nextSession = await call("/api/session");
    const nextItem = await call("/api/catalog/" + nextSession.question_version_id);
    const nextPapers = await call("/api/practice/papers");
    setSession(nextSession);
    setItem(nextItem);
    setPapers(nextPapers.papers);
    if (!nextSession.student_ids.includes(studentId) && nextSession.student_ids[0]) {
      setStudentId(nextSession.student_ids[0]);
    }
  }

  useEffect(() => {
    load().catch((reason) => setError(reason.message));
  }, []);

  async function run(action) {
    setError("");
    setMessage("");
    try {
      await action();
    } catch (reason) {
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

  function issue() {
    return run(async () => {
      const opened = await call("/api/practice/papers", {
        method: "POST",
        body: JSON.stringify({
          teacher_id: session.actor_teacher_id,
          student_id: studentId,
          subject_id: item.subject_id,
          question_version_id: item.question_version_id,
          review_version_id: REVIEW_VERSION_ID,
        }),
      });
      setPaper(opened);
      setConfirmation(null);
      const nextAttempt = await call("/api/practice/papers/" + opened.paper_id + "/attempt");
      setAttempt(nextAttempt);
      const nextPapers = await call("/api/practice/papers");
      setPapers(nextPapers.papers);
      setMessage(opened.status === "可打印" ? "已出卷，可以打开 PDF" : "已出卷，仍待渲染");
    });
  }

  function handOut() {
    return run(async () => {
      const next = await call("/api/practice/papers/" + paper.paper_id + "/handout", {
        method: "POST",
        body: "{}",
      });
      setPaper({ ...paper, ...next });
      const nextPapers = await call("/api/practice/papers");
      setPapers(nextPapers.papers);
      setMessage("已发放");
    });
  }

  function choosePaper(row) {
    return run(async () => {
      setPaper(row);
      setConfirmation(null);
      const nextAttempt = await call("/api/practice/papers/" + row.paper_id + "/attempt");
      setAttempt(nextAttempt);
      setMessage("已打开卷 " + row.paper_id);
    });
  }

  function confirm() {
    return run(async () => {
      const result = await call("/api/practice/confirmations", {
        method: "POST",
        body: JSON.stringify({
          operation_key: operationKey,
          paper_id: paper.paper_id,
          sub_question_id: attempt.sub_question_id,
          teacher_id: session.actor_teacher_id,
          review_version_id: attempt.review_version_id,
          decision,
          fixture_answer_id: attempt.fixture_answer_id,
        }),
      });
      setConfirmation(result);
      setMessage("确认号 " + result.confirmation_id + "，正式记录 " + result.count + " 条");
    });
  }

  const approved = Boolean(item && item.question_approved && item.answer_approved);

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
        <button type="button" onClick={issue} disabled={!approved}>
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
        {paper && paper.file_id && (
          <p>
            <a href={"/api/practice/files/" + paper.file_id} target="_blank" rel="noreferrer">
              打开 PDF
            </a>
          </p>
        )}
        {paper && paper.status === "可打印" && (
          <button type="button" onClick={handOut}>
            正式发放
          </button>
        )}
        {papers.length > 0 && (
          <ul>
            {papers.map((row) => (
              <li key={row.paper_id}>
                <button type="button" onClick={() => choosePaper(row)}>
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
          <p>
            待确认作答 {attempt.fixture_answer_id}，小问 {attempt.sub_question_id}，复核{" "}
            {attempt.review_version_id}
          </p>
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
        <button type="button" onClick={confirm} disabled={!attempt}>
          确认
        </button>
        <button type="button" onClick={confirm} disabled={!confirmation}>
          同键重试
        </button>
        {confirmation && (
          <p className="ok">
            确认号 {confirmation.confirmation_id}，正式记录 {confirmation.count} 条
          </p>
        )}
      </section>
    </main>
  );
}
