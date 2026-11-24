/** Read-only recognition status. Adopting a suggestion is a later batch. */

import { useEffect, useState } from "react";

const TEACHER_LOOK = 0.6;

const VERDICT = {
  correct: "对",
  incorrect: "错",
  partial: "部分对",
  unsure: "不确定",
};

const JUDGED = {
  local: "本机判",
  model: "模型判",
};

const REASON = {
  timeout: "超时",
  auth_failed: "鉴权失败",
  model_output_invalid: "输出不合格",
  network: "网络不通",
  interrupted: "中断",
  model_not_found: "模型不对",
  ai_provider_incomplete: "未配置",
  failed: "失败",
  ai_daily_limit: "已达今日上限",
  ai_run_in_progress: "识别中",
};

export function AiPanel({ intakeId, call, initialRun }) {
  const storageKey = "k12-ai-run:" + intakeId;
  const [run, setRun] = useState(initialRun || null);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const status = run ? run.status : "";
  const runId = run ? run.run_id : "";

  useEffect(() => {
    if (initialRun) return undefined;
    const saved = sessionStorage.getItem(storageKey);
    if (!saved) return undefined;
    let stop = false;
    call("/api/practice/ai-runs/" + saved)
      .then((body) => {
        if (!stop) setRun(body);
      })
      .catch((reason) => {
        if (!stop) setNote(label(reason && reason.code));
      });
    return () => {
      stop = true;
    };
  }, [storageKey, initialRun, call]);

  useEffect(() => {
    if (status !== "queued" && status !== "running") return undefined;
    if (!runId) return undefined;
    const timer = setInterval(() => {
      call("/api/practice/ai-runs/" + runId)
        .then((body) => setRun(body))
        .catch((reason) => setNote(label(reason && reason.code)));
    }, 400);
    return () => clearInterval(timer);
  }, [status, runId, call]);

  function start() {
    if (pending) return;
    setPending(true);
    setNote("");
    call("/api/practice/intake/" + intakeId + "/ai-runs", { method: "POST", body: "{}" })
      .then((body) => {
        sessionStorage.setItem(storageKey, body.run_id);
        setRun({ run_id: body.run_id, status: body.status || "queued", suggestions: [] });
      })
      .catch((reason) => setNote(label(reason && reason.code)))
      .finally(() => setPending(false));
  }

  const busy = pending || status === "queued" || status === "running";
  const mismatch = run && (run.external_match === "mismatch" || run.page_match === "mismatch");
  const failed = status === "failed";

  return (
    <div className="ai-panel">
      <p className="note">AI 建议，老师确认前不算结果</p>
      {mismatch ? <p className="error">照片上的学号或页码和这张卷对不上，请核对</p> : null}
      <p>状态：{statusText(status)}</p>
      {failed ? <p>{label(run.error_code)}</p> : null}
      {note ? <p>{note}</p> : null}
      <button type="button" onClick={start} disabled={busy}>
        {failed ? "重试" : "AI 识别"}
      </button>
      {status === "succeeded" ? (
        <ul>
          {(run.suggestions || []).map((item) => (
            <li key={item.order_no}>
              转写 {item.transcription} 置信度 {item.confidence} 建议 {VERDICT[item.verdict] || item.verdict} 依据{" "}
              {item.reason} {JUDGED[item.judged_by] || item.judged_by}
              {item.unreadable || item.confidence < TEACHER_LOOK ? " 需要老师看" : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function statusText(status) {
  if (status === "queued" || status === "running") return "识别中";
  if (status === "succeeded") return "完成";
  if (status === "failed") return "失败";
  return "未识别";
}

function label(code) {
  return REASON[code] || "失败";
}
