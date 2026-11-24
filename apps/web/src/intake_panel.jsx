/** Whole-page intake. The server checks the paper, the page, and the teacher again. */

import { useEffect, useRef, useState } from "react";
import { preparePhoto, splitPayload } from "./intake_decode.js";

export function IntakePanel({ papers, call, initialShots }) {
  const [shots, setShots] = useState(initialShots || []);
  const [progress, setProgress] = useState({});
  const [tick, setTick] = useState(0);
  const busy = useRef(new Set());
  const camera = useRef(null);
  const album = useRef(null);

  useEffect(() => {
    let stop = false;
    if (!papers.length) {
      setProgress({});
      return undefined;
    }
    Promise.all(
      papers.map((paper) =>
        call("/api/practice/papers/" + paper.paper_id + "/intake")
          .then((body) => [paper.paper_id, body])
          .catch(() => [paper.paper_id, null]),
      ),
    ).then((rows) => {
      if (!stop) setProgress(Object.fromEntries(rows));
    });
    return () => {
      stop = true;
    };
  }, [papers, call, tick]);

  useEffect(() => {
    for (const shot of shots) {
      if (shot.phase !== "ready" || busy.current.has(shot.id)) continue;
      const paper = papers.find((row) => row.paper_id === shot.paperId);
      if (!paper) {
        patch(setShots, shot.id, { phase: "missing" });
        continue;
      }
      send(shot, paper.paper_id, shot.pageNo, "qr", false);
    }
  }, [shots, papers]);

  function send(shot, paperId, pageNo, locatedBy, replace) {
    if (!shot.blob) return;
    busy.current.add(shot.id);
    patch(setShots, shot.id, { phase: "sending", holdPaper: paperId, holdPage: pageNo, holdBy: locatedBy });
    const query = "?located_by=" + locatedBy + (replace ? "&replace=true" : "");
    const headers = { "Content-Type": "image/jpeg", Accept: "application/json" };
    if (locatedBy === "qr" && shot.payload) headers["X-K12-Qr"] = shot.payload;
    call("/api/practice/papers/" + paperId + "/pages/" + pageNo + "/intake" + query, {
      method: "PUT",
      body: shot.blob,
      headers,
    })
      .then(() => {
        busy.current.delete(shot.id);
        patch(setShots, shot.id, { phase: "done", note: "已收" });
        setTick((value) => value + 1);
      })
      .catch((reason) => {
        busy.current.delete(shot.id);
        if (reason && reason.code === "page_already_received") {
          patch(setShots, shot.id, {
            phase: "ask-replace",
            note: "替换吗",
            holdPaper: paperId,
            holdPage: pageNo,
            holdBy: locatedBy,
          });
          return;
        }
        patch(setShots, shot.id, { phase: "failed", note: (reason && reason.code) || "上传失败" });
      });
  }

  async function take(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    for (const file of files) {
      const prepared = await preparePhoto(file);
      const parsed = splitPayload(prepared.payload);
      const shot = {
        id: "shot-" + Date.now() + "-" + file.name,
        thumb: prepared.thumb,
        blob: prepared.blob,
        payload: prepared.payload,
        paperId: parsed ? parsed.paperId : "",
        pageNo: parsed ? parsed.page : 0,
        manualPaperId: "",
        phase: parsed ? "ready" : "unread",
        note: "",
      };
      setShots((rows) => [...rows, shot]);
    }
  }

  function assignPaper(shot, paperId) {
    patch(setShots, shot.id, { manualPaperId: paperId });
  }

  function assignPage(shot, pageNo) {
    const page = Number(pageNo);
    if (!shot.manualPaperId || !page) return;
    patch(setShots, shot.id, { pageNo: page, phase: "picked" });
    send({ ...shot, blob: shot.blob, payload: "" }, shot.manualPaperId, page, "manual", false);
  }

  return (
    <section className="intake">
      <h2>收卷</h2>
      <p className="note">拍照或从相册选。读不出二维码时，从自己出过的卷里选一页。</p>
      <label className="intake-file">
        拍照
        <input ref={camera} type="file" accept="image/*" capture="environment" onChange={take} />
      </label>
      <label className="intake-file">
        从相册选
        <input ref={album} type="file" accept="image/*" multiple onChange={take} />
      </label>
      <ul>
        {shots.map((shot) => (
          <li key={shot.id}>
            {shot.thumb ? <img src={shot.thumb} alt="" /> : null}
            <p>{caption(shot, papers)}</p>
            {shot.phase === "unread" && (
              <>
                <label>
                  选择卷
                  <select
                    aria-label="选择卷"
                    value={shot.manualPaperId || ""}
                    onChange={(event) => assignPaper(shot, event.target.value)}
                  >
                    <option value="">选择卷</option>
                    {groups(papers).map(([day, rows]) => (
                      <optgroup key={day} label={day}>
                        {rows.map((paper) => (
                          <option key={paper.paper_id} value={paper.paper_id}>
                            {numberOf(paper)} · {day}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
                <label>
                  选择页
                  <select
                    aria-label="选择页"
                    value=""
                    onChange={(event) => assignPage(shot, event.target.value)}
                  >
                    <option value="">选择页</option>
                    {pageOptions(papers, shot.manualPaperId).map((page) => (
                      <option key={page} value={page}>
                        第 {page} 页
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {shot.note ? <p>{shot.note}</p> : null}
            {shot.phase === "ask-replace" && (
              <button
                type="button"
                onClick={() => send(shot, shot.holdPaper, shot.holdPage, shot.holdBy, true)}
              >
                替换
              </button>
            )}
          </li>
        ))}
      </ul>
      {papers.length > 0 && (
        <>
          <h3>缺页</h3>
          <ul>
            {papers.map((paper) => {
              const body = progress[paper.paper_id];
              const received = body ? body.pages.filter((page) => page.received).length : 0;
              const total = body ? body.page_count : paper.page_count;
              const missing = body ? body.pages.filter((page) => !page.received).map((page) => page.page_no) : [];
              return (
                <li key={paper.paper_id}>
                  {numberOf(paper)}：已收 {received} / {total} 页
                  {missing.length ? "，缺第 " + missing.join("、") + " 页" : ""}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

function caption(shot, papers) {
  if (!shot.payload) return "未识别";
  const paper = papers.find((row) => row.paper_id === shot.paperId);
  if (!paper) return "读到码，但不在你出过的卷里";
  return numberOf(paper) + "，第 " + shot.pageNo + " / " + paper.page_count + " 页";
}

function numberOf(paper) {
  return paper.printed_external_id ? "学号 " + paper.printed_external_id : "学号未记下";
}

function groups(papers) {
  const map = new Map();
  for (const paper of papers) {
    const day = paper.issued_on || "未记下日期";
    const rows = map.get(day) || [];
    rows.push(paper);
    map.set(day, rows);
  }
  return Array.from(map.entries());
}

function pageOptions(papers, paperId) {
  const paper = papers.find((row) => row.paper_id === paperId);
  const count = paper && paper.page_count ? paper.page_count : 0;
  return Array.from({ length: count }, (_, index) => index + 1);
}

function patch(setShots, id, fields) {
  setShots((rows) => rows.map((row) => (row.id === id ? { ...row, ...fields } : row)));
}
