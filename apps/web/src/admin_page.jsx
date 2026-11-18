import { useEffect, useState } from "react";
import { call, callWithId } from "./auth.js";

const EMPTY = { username: "", secret: "", name: "", grade: "", subjectId: "", teacherId: "", studentId: "" };

export function AdminPage() {
  const [teachers, setTeachers] = useState([]);
  const [students, setStudents] = useState([]);
  const [grants, setGrants] = useState([]);
  const [audit, setAudit] = useState([]);
  const [errors, setErrors] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState(null);

  async function reload() {
    const [teacherRows, studentRows, grantRows, auditRows, errorRows] = await Promise.all([
      call("/api/admin/teachers"),
      call("/api/admin/students"),
      call("/api/admin/grants"),
      call("/api/admin/audit"),
      call("/api/admin/errors"),
    ]);
    setTeachers(teacherRows.teachers || []);
    setStudents(studentRows.students || []);
    setGrants(grantRows.grants || []);
    setAudit(auditRows.events || []);
    setErrors(errorRows.errors || []);
  }

  useEffect(() => {
    reload().catch(setError);
  }, []);

  function setField(key) {
    return (event) => setForm((current) => ({ ...current, [key]: event.target.value }));
  }

  async function write(path, body, clear) {
    setError(null);
    setNotice("");
    try {
      const result = await callWithId(path, { method: "POST", body: JSON.stringify(body) });
      setNotice("request_id " + (result.requestId || ""));
      if (clear) setForm((current) => ({ ...current, ...clear }));
      await reload();
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <main className="wide">
      <h1>管理</h1>
      {notice && <p className="note">{notice}</p>}
      {error && (
        <p className="error">
          {error.code}：{error.message}
          {error.request_id ? " " + error.request_id : ""}
        </p>
      )}
      <section>
        <h2>老师</h2>
        <label>用户名<input name="teacher-username" value={form.username} onChange={setField("username")} /></label>
        <label>口令<input name="teacher-secret" type="password" value={form.secret} onChange={setField("secret")} /></label>
        <label>老师编号<input name="teacher-id" value={form.teacherId} onChange={setField("teacherId")} /></label>
        <button type="button" onClick={() => write("/api/admin/teachers", { username: form.username, secret: form.secret }, { username: "", secret: "" })}>
          创建老师
        </button>
        <button type="button" onClick={() => write("/api/admin/teachers/" + form.teacherId + "/password", { secret: form.secret }, { secret: "" })}>
          重置口令
        </button>
        <People rows={teachers} idKey="user_id" label={(row) => row.username + " · " + row.status} onDisable={(id) => write("/api/admin/teachers/" + id + "/disable", {})} onEnable={(id) => write("/api/admin/teachers/" + id + "/enable", {})} />
      </section>
      <section>
        <h2>学生</h2>
        <label>姓名<input name="student-name" value={form.name} onChange={setField("name")} /></label>
        <label>年级<input name="student-grade" value={form.grade} onChange={setField("grade")} /></label>
        <label>学科<input name="student-subject" value={form.subjectId} onChange={setField("subjectId")} /></label>
        <button type="button" onClick={() => write("/api/admin/students", { name: form.name, grade: form.grade, subject_id: form.subjectId }, { name: "", grade: "", subjectId: "" })}>
          创建学生
        </button>
        <People rows={students} idKey="student_id" label={(row) => row.student_id + " · " + row.status} onArchive={(id) => write("/api/admin/students/" + id + "/archive", {})} />
      </section>
      <section>
        <h2>授权</h2>
        <label>老师编号<input name="grant-teacher" value={form.teacherId} onChange={setField("teacherId")} /></label>
        <label>学生编号<input name="grant-student" value={form.studentId} onChange={setField("studentId")} /></label>
        <label>学科<input name="grant-subject" value={form.subjectId} onChange={setField("subjectId")} /></label>
        <button type="button" onClick={() => write("/api/admin/grants", { teacher_id: form.teacherId, student_id: form.studentId, subject_id: form.subjectId })}>
          授权
        </button>
        <ul>
          {grants.map((row) => (
            <li key={row.grant_id}>
              {row.teacher_id} · {row.student_id} · {row.subject_id} · {row.revoked ? "已撤销" : "有效"}
              {!row.revoked && (
                <button type="button" onClick={() => write("/api/admin/grants/revoke", { teacher_id: row.teacher_id, student_id: row.student_id, subject_id: row.subject_id })}>
                  撤销
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>审计与错误</h2>
        <button type="button" onClick={() => reload().catch(setError)}>刷新</button>
        <h3>审计</h3>
        <ul>
          {audit.map((row) => (
            <li key={row.request_id + row.action + row.occurred_at}>
              {row.action} · {row.outcome} · {row.request_id}
            </li>
          ))}
        </ul>
        <h3>错误</h3>
        <ul>
          {errors.map((row) => (
            <li key={row.request_id + row.event + row.time}>
              {row.event} · {row.outcome} · {row.request_id}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

function People({ rows, idKey, label, onDisable, onEnable, onArchive }) {
  return (
    <ul>
      {rows.map((row) => {
        const id = row[idKey];
        return (
          <li key={id}>
            {label(row)}
            {onDisable && <button type="button" onClick={() => onDisable(id)}>停用</button>}
            {onEnable && <button type="button" onClick={() => onEnable(id)}>启用</button>}
            {onArchive && <button type="button" onClick={() => onArchive(id)}>归档</button>}
          </li>
        );
      })}
    </ul>
  );
}
