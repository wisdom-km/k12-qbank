import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "./auth.js";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState(null);

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    try {
      const row = await login(username, secret);
      navigate(row.role === "admin" ? "/admin" : "/", { replace: true });
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <main>
      <h1>登录</h1>
      <form onSubmit={onSubmit}>
        <label>
          用户名
          <input name="username" value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          口令
          <input
            name="secret"
            type="password"
            value={secret}
            onChange={(event) => setSecret(event.target.value)}
          />
        </label>
        <button type="submit">登录</button>
      </form>
      {error && (
        <p className="error">
          {error.code}：{error.message}
        </p>
      )}
    </main>
  );
}
