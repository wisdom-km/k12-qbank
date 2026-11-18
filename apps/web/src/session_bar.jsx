import { useState, useSyncExternalStore } from "react";
import { useNavigate } from "react-router-dom";
import { getSession, logout, subscribe } from "./auth.js";

export function SessionBar() {
  const navigate = useNavigate();
  const session = useSyncExternalStore(subscribe, getSession, getSession);
  const [error, setError] = useState(null);
  if (!session) return null;

  async function onLogout() {
    setError(null);
    try {
      await logout();
      navigate("/login", { replace: true });
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <header className="bar">
      <p>
        已登录：{session.role} {session.display_name}
      </p>
      <button type="button" onClick={onLogout}>
        注销
      </button>
      {error && (
        <p className="error">
          {error.code}：{error.message}
          {error.request_id ? " " + error.request_id : ""}
        </p>
      )}
    </header>
  );
}
