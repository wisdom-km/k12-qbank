/** One paper, one conclusion per item. A suggestion is not a result until the teacher saves it. */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { preparePhoto } from "./intake_decode.js";

const VERDICT = {
  correct: "对",
  incorrect: "错",
  partial: "部分对",
  blank: "空白",
  unsure: "不确定",
};

const JUDGED = {
  local: "本机判",
  model: "模型判",
};

const TYPE = {
  single_choice: "选择",
  multiple_choice: "多选",
  fill_blank: "填空",
  solution: "解答",
  composite: "综合",
};

const REFUSAL = {
  cannot_adopt_unsure: "不确定的建议不能采用",
  suggestion_stale: "这张照片已经换过，请重新识别或手评",
  suggestion_required: "当前没有建议，请手评",
};

const RETRY = ["incorrect", "partial", "blank"];

const FOLLOW = {
  no_retry_items: "暂无可再练的已确认错题",
  decision_required: "有题还没有老师结论，不能再出练习",
  invalid_order_no: "题号无效",
  retired: "有题已经停用，不能再出练习",
  question_retired: "有题已经停用，不能再出练习",
  formula_unsupported: "有公式暂不支持排版，不能再出练习",
  formula_unstructured: "有公式还没拆开，不能再出练习",
  formula_too_wide: "有公式比一行宽，不能再出练习",
  item_too_long: "有题放不进一页，不能再出练习",
  permission_denied: "没有权限为这张卷再出练习",
  not_found: "找不到这张卷",
};

export function GradePage({ paperId, call }) {
  const [review, setReview] = useState(null);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState(null);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({ verdict: "correct", transcript: "", comment: "" });
  const [pageNo, setPageNo] = useState("1");
  const [picked, setPicked] = useState([]);
  const [follow, setFollow] = useState(null);
  const [followCount, setFollowCount] = useState(0);
  const [followNote, setFollowNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stop = false;
    call("/api/practice/papers/" + paperId + "/review")
      .then((body) => {
        if (!stop) {
          setReview(body);
          setPicked(defaultRetry(body));
        }
      })
      .catch((reason) => {
        if (!stop) setNote(label(reason));
      });
    return () => {
      stop = true;
    };
  }, [paperId, call]);

  function refresh(body) {
    setReview(body);
    setPicked(defaultRetry(body));
    setNote("");
    setEditing(null);
  }

  function fail(reason) {
    setNote(label(reason));
  }

  function adopt(orderNo) {
    call(decisionUrl(paperId, orderNo), { method: "PUT", body: JSON.stringify({ action: "adopt" }) })
      .then(() => call("/api/practice/papers/" + paperId + "/review"))
      .then(refresh)
      .catch(fail);
  }

  function openEditor(orderNo, action) {
    setEditing({ orderNo, action });
    setDraft({ verdict: "correct", transcript: "", comment: "" });
    setNote("");
  }

  function saveEditor(event) {
    event.preventDefault();
    if (!editing) return;
    call(decisionUrl(paperId, editing.orderNo), {
      method: "PUT",
      body: JSON.stringify({
        action: editing.action,
        verdict: draft.verdict,
        corrected_transcription: draft.transcript,
        comment: draft.comment,
      }),
    })
      .then(() => call("/api/practice/papers/" + paperId + "/review"))
      .then(refresh)
      .catch(fail);
  }

  function askBulk() {
    setPreview(confidentOrders(review));
    setNote("");
  }

  function confirmBulk() {
    call("/api/practice/papers/" + paperId + "/decisions/adopt-confident", {
      method: "POST",
      body: "{}",
    })
      .then(() => call("/api/practice/papers/" + paperId + "/review"))
      .then((body) => {
        setPreview(null);
        refresh(body);
      })
      .catch(fail);
  }

  async function relocate(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    try {
      const photo = await preparePhoto(file);
      const query = "?located_by=manual&replace=true";
      await call("/api/practice/papers/" + paperId + "/pages/" + pageNo + "/intake" + query, {
        method: "PUT",
        body: photo.blob,
        headers: { "Content-Type": "image/jpeg" },
      });
      refresh(await call("/api/practice/papers/" + paperId + "/review"));
    } catch (reason) {
      fail(reason);
    }
  }

  function toggleRetry(orderNo) {
    setPicked((current) => {
      const next = current.includes(orderNo)
        ? current.filter((value) => value !== orderNo)
        : current.concat(orderNo);
      return next.slice().sort((left, right) => left - right);
    });
  }

  function followUp() {
    const orderNos = picked.slice();
    setBusy(true);
    setFollowNote("");
    call("/api/practice/papers/" + paperId + "/follow-up", {
      method: "POST",
      body: JSON.stringify({ order_nos: orderNos }),
    })
      .then((body) => {
        setFollow(body);
        setFollowCount(orderNos.length);
        setBusy(false);
      })
      .catch((reason) => {
        setFollowNote(followLabel(reason));
        setBusy(false);
      });
  }

  function handFollow() {
    if (!follow) return;
    setBusy(true);
    setFollowNote("");
    call("/api/practice/papers/" + follow.paper_id + "/handout", { method: "POST", body: "{}" })
      .then((body) => {
        setFollow(body);
        setBusy(false);
      })
      .catch((reason) => {
        setFollowNote(followLabel(reason));
        setBusy(false);
      });
  }

  const items = review ? ranked(review.items || []) : [];
  const confirmed = items.filter((item) => item.decision);
  const mismatch = review ? review.mismatch_pages || [] : [];

  return (
    <main className="grade">
      <p>
        <Link to="/">返回收卷</Link>
      </p>
      <h1>批改</h1>
      <p className="note">AI 建议只有经老师采用或改判后才算结果</p>
      {review ? (
        <p>
          已确认 {review.confirmed} / 共 {review.total}，对 {review.correct} 题
          {review.done ? " 已批完" : ""}
        </p>
      ) : null}
      {mismatch.length ? (
        <p className="error">照片上的学号或页码和这张卷对不上，请核对</p>
      ) : null}
      {mismatch.length ? (
        <div>
          <label>
            页
            <select aria-label="重新定位的页" value={pageNo} onChange={(event) => setPageNo(event.target.value)}>
              {mismatch.map((page) => (
                <option key={page} value={page}>
                  第 {page} 页
                </option>
              ))}
            </select>
          </label>
          <label className="intake-file">
            重新定位这张照片
            <input type="file" accept="image/*" aria-label="重新定位这张照片" onChange={relocate} />
          </label>
        </div>
      ) : null}
      <button type="button" onClick={askBulk}>
        采用全部高把握的本机判结果
      </button>
      {preview ? (
        <div role="dialog" aria-label="确认采用">
          <p>{preview.length ? "将采用第 " + preview.join("、") + " 题" : "没有可一次采用的题"}</p>
          <button type="button" onClick={confirmBulk} disabled={!preview.length}>
            确认采用
          </button>
          <button type="button" onClick={() => setPreview(null)}>
            取消
          </button>
        </div>
      ) : null}
      {note ? <p className="error">{note}</p> : null}
      <ol>
        {items.map((item) => (
          <li key={item.order_no} className={item.suggestion && item.suggestion.needs_review ? "needs-review" : ""}>
            <p>
              题 {item.order_no} {TYPE[item.question_type] || item.question_type} {snippet(item.stem)}
            </p>
            <p>标准答案 {item.standard_answer}</p>
            <p>收卷 {item.intake_status === "received" ? "已收" : "未收"}</p>
            {item.stale ? <p>这张照片已经换过，请重新识别或手评</p> : null}
            {item.suggestion ? (
              <p>
                转写 {item.suggestion.transcription} 建议 {VERDICT[item.suggestion.verdict] || item.suggestion.verdict}{" "}
                置信度 {item.suggestion.confidence} {JUDGED[item.suggestion.judged_by] || item.suggestion.judged_by}
                {item.suggestion.needs_review ? " 需要老师看" : ""}
              </p>
            ) : (
              <p>没有 AI 建议</p>
            )}
            {item.decision ? (
              <p>
                老师结论 {VERDICT[item.decision.verdict] || item.decision.verdict}
                {item.decision.comment ? " 评语 " + item.decision.comment : ""}
              </p>
            ) : null}
            <div className="grade-actions">
              {item.suggestion && !item.stale ? (
                <button type="button" onClick={() => adopt(item.order_no)} disabled={item.suggestion.verdict === "unsure"}>
                  采用
                </button>
              ) : null}
              {item.suggestion && !item.stale ? (
                <button type="button" onClick={() => openEditor(item.order_no, "revise")}>
                  改判
                </button>
              ) : null}
              {!item.suggestion || item.stale ? (
                <button type="button" onClick={() => openEditor(item.order_no, "manual")}>
                  手评
                </button>
              ) : null}
            </div>
            {editing && editing.orderNo === item.order_no ? (
              <form onSubmit={saveEditor}>
                <label>
                  结论
                  <select
                    aria-label="结论"
                    value={draft.verdict}
                    onChange={(event) => setDraft({ ...draft, verdict: event.target.value })}
                  >
                    <option value="correct">对</option>
                    <option value="incorrect">错</option>
                    <option value="partial">部分对</option>
                    <option value="blank">空白</option>
                  </select>
                </label>
                <label>
                  修正转写
                  <input
                    aria-label="修正转写"
                    value={draft.transcript}
                    onChange={(event) => setDraft({ ...draft, transcript: event.target.value })}
                  />
                </label>
                <label>
                  评语
                  <input
                    aria-label="评语"
                    value={draft.comment}
                    onChange={(event) => setDraft({ ...draft, comment: event.target.value })}
                  />
                </label>
                <button type="submit">{editing.action === "manual" ? "保存手评" : "保存改判"}</button>
              </form>
            ) : null}
          </li>
        ))}
      </ol>
      {review ? (
        <section className="follow-up" aria-label="再出一份练习">
          <h2>再出一份练习</h2>
          <ul>
            {confirmed.map((item) => (
              <li key={item.order_no}>
                <label>
                  <input
                    type="checkbox"
                    aria-label={"再练题 " + item.order_no}
                    checked={picked.includes(item.order_no)}
                    onChange={() => toggleRetry(item.order_no)}
                  />
                  题 {item.order_no} {VERDICT[item.decision.verdict] || item.decision.verdict}
                </label>
              </li>
            ))}
          </ul>
          {picked.length === 0 ? <p>暂无可再练的已确认错题</p> : null}
          <button type="button" onClick={followUp} disabled={picked.length === 0 || busy}>
            再出一份练习
          </button>
          {followNote ? <p className="error">{followNote}</p> : null}
          {follow ? (
            <div>
              <p>新卷号 {follow.paper_id}</p>
              <p>包含 {followCount} 题</p>
              <p>状态 {follow.status}</p>
              {follow.file_id ? (
                <p>
                  <a href={"/api/practice/files/" + follow.file_id}>打开 PDF</a>
                </p>
              ) : null}
              <button type="button" onClick={handFollow} disabled={busy}>
                正式发放
              </button>
              <p>
                <Link to="/">返回老师页</Link>
              </p>
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}

function ranked(items) {
  return [...items].sort((left, right) => {
    const leftFirst = left.suggestion && left.suggestion.needs_review ? 0 : 1;
    const rightFirst = right.suggestion && right.suggestion.needs_review ? 0 : 1;
    if (leftFirst !== rightFirst) return leftFirst - rightFirst;
    return left.order_no - right.order_no;
  });
}

function confidentOrders(review) {
  if (!review) return [];
  return (review.items || [])
    .filter((item) => {
      const suggestion = item.suggestion;
      if (!suggestion || item.decision) return false;
      return (
        suggestion.judged_by === "local" &&
        suggestion.confidence >= review.threshold &&
        suggestion.verdict !== "unsure"
      );
    })
    .map((item) => item.order_no);
}

function defaultRetry(review) {
  return (review && review.items ? review.items : [])
    .filter((item) => item.decision && RETRY.includes(item.decision.verdict))
    .map((item) => item.order_no)
    .sort((left, right) => left - right);
}

function followLabel(reason) {
  const code = reason && reason.code;
  return FOLLOW[code] || (reason && reason.message) || "再出练习失败";
}

function decisionUrl(paperId, orderNo) {
  return "/api/practice/papers/" + paperId + "/items/" + orderNo + "/decision";
}

function snippet(stem) {
  const text = String(stem || "");
  return text.length > 24 ? text.slice(0, 24) + "…" : text;
}

function label(reason) {
  const code = reason && reason.code;
  return REFUSAL[code] || (reason && reason.message) || "失败";
}
