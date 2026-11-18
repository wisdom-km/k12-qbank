import { useState } from "react";
import { call } from "./auth.js";

export function AccountPage() {
  const [oldSecret, setOldSecret] = useState("");
  const [newSecret, setNewSecret] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState(null);

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    setNotice("");
    try {
      await call("/api/account/password", {
        method: "POST",
        body: JSON.stringify({ old_secret: oldSecret, new_secret: newSecret }),
      });
      setOldSecret("");
      setNewSecret("");
      setNotice("口令已更新");
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <main>
      <h1>修改我的口令</h1>
      <form onSubmit={onSubmit}>
        <label>
          原口令
          <input
            name="old_secret"
            type="password"
            value={oldSecret}
            onChange={(event) => setOldSecret(event.target.value)}
          />
        </label>
        <label>
          新口令
          <input
            name="new_secret"
            type="password"
            value={newSecret}
            onChange={(event) => setNewSecret(event.target.value)}
          />
        </label>
        <button type="submit">保存口令</button>
      </form>
      {notice && <p className="ok">{notice}</p>}
      {error && (
        <p className="error">
          {error.code}：{error.message}
        </p>
      )}
    </main>
  );
}
