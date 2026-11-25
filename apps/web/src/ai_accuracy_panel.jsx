import { useEffect, useRef, useState } from "react";
import { call } from "./auth.js";

export function AiAccuracyPanel() {
  const generation = useRef(0);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    void load("");
  }, []);

  async function load(next) {
    const ticket = generation.current + 1;
    generation.current = ticket;
    setBusy(true);
    setError(null);
    const query = next ? "?" + next : "";
    try {
      const body = await call("/api/admin/ai/accuracy" + query);
      if (generation.current !== ticket) return;
      setReport(body);
    } catch (reason) {
      if (generation.current !== ticket) return;
      setError(reason);
    } finally {
      if (generation.current === ticket) setBusy(false);
    }
  }

  function onModel(event) {
    const next = event.target.value;
    setChoice(next);
    void load(next);
  }

  const models = (report && report.available_models) || [];

  return (
    <section>
      <h2>识别率对账</h2>
      <label>
        模型
        <select name="accuracy-model" value={choice} onChange={onModel} disabled={busy}>
          <option value="">全部</option>
          {models.map((row) => {
            const query = "provider=" + encodeURIComponent(row.provider) + "&model=" + encodeURIComponent(row.model);
            return (
              <option key={query} value={query}>
                {row.provider} / {row.model}
              </option>
            );
          })}
        </select>
      </label>
      <button type="button" onClick={() => load(choice)} disabled={busy}>
        {busy ? "正在读取…" : "刷新对账"}
      </button>
      {error && (
        <p className="error">
          {error.code}：{error.message}
          {error.request_id ? " " + error.request_id : ""}
        </p>
      )}
      {report && <Report report={report} />}
    </section>
  );
}

function Report({ report }) {
  if (isEmpty(report)) {
    return (
      <p className="note">
        暂无已完成对账的 AI 识别记录。当前阈值 {shown(report.current_threshold)}。
      </p>
    );
  }
  const runs = report.runs || {};
  const items = report.items || {};
  const external = runs.external_match || {};
  const page = runs.page_match || {};
  const judged = items.by_judged_by || {};
  const failed = runs.failed_by_code || {};
  return (
    <div>
      <p className="note">当前阈值 {shown(report.current_threshold)}</p>
      <h3>运行</h3>
      <p>
        成功 {runs.succeeded}，失败 {runs.failed}，进行中 {runs.active}
      </p>
      {Object.keys(failed).length > 0 && (
        <p>
          失败原因{" "}
          {Object.entries(failed)
            .map(([code, count]) => code + " " + count)
            .join("，")}
        </p>
      )}
      <p>
        学号匹配：一致 {external.matched}，不一致 {external.mismatched}，未读到 {external.missing}
      </p>
      <p>
        页码匹配：一致 {page.matched}，不一致 {page.mismatched}，未读到 {page.missing}
      </p>
      <p>
        输入 token {runs.input_tokens}，输出 token {runs.output_tokens}
      </p>
      <h3>对账</h3>
      <p>
        已批改 {items.decided_total}，关联 AI {items.linked_ai}，未关联 {items.unlinked_manual}，总体一致率 {shown(items.agreement_rate)}
      </p>
      <p>本地判分：{judgeLine(judged.local)}</p>
      <p>模型判分：{judgeLine(judged.model)}</p>
      <h3>阈值测算</h3>
      <div className="report-scroll">
        <table>
          <thead>
            <tr>
              <th>阈值</th>
              <th>高把握题数</th>
              <th>覆盖率</th>
              <th>高把握一致率</th>
              <th>高把握误判</th>
              <th>需老师复核</th>
            </tr>
          </thead>
          <tbody>
            {(report.thresholds || []).map((row) => (
              <tr key={String(row.threshold)}>
                <td>{shown(row.threshold)}</td>
                <td>{row.confident_count}</td>
                <td>{shown(row.coverage_rate)}</td>
                <td>{shown(row.confident_accuracy)}</td>
                <td className="hint">{row.false_confident}</td>
                <td>{row.review_needed_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function isEmpty(report) {
  const runs = report.runs || {};
  const items = report.items || {};
  return (runs.total || 0) === 0 && (items.decided_total || 0) === 0;
}

function judgeLine(row) {
  if (!row) return "—";
  return "题数 " + row.total + "，可判定 " + row.decisive + "，一致 " + row.agreed + "，不一致 " + row.disagreed + "，一致率 " + shown(row.agreement_rate);
}

function shown(value) {
  if (value === null || value === undefined) return "—";
  return String(value);
}
