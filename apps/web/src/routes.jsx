import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { bindUnauthenticated, loadSession, notePath } from "./auth.js";
import { AdminPage } from "./admin_page.jsx";
import { LoginPage } from "./login_page.jsx";
import { SessionBar } from "./session_bar.jsx";
import { TeacherPage } from "./teacher_page.jsx";

export function AppRoutes() {
  const navigate = useNavigate();
  const location = useLocation();
  notePath(location.pathname);
  useEffect(() => {
    bindUnauthenticated(() => {
      if (location.pathname !== "/login") navigate("/login", { replace: true });
    });
  }, [location.pathname, navigate]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Guard><TeacherPage /></Guard>} />
      <Route path="/admin" element={<Guard admin><AdminPage /></Guard>} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

function Guard({ children, admin = false }) {
  const navigate = useNavigate();
  const [state, setState] = useState("loading");

  useEffect(() => {
    let live = true;
    loadSession()
      .then((row) => {
        if (!live) return;
        if (!row) {
          navigate("/login", { replace: true });
          return;
        }
        if (admin && row.role !== "admin") {
          setState("forbidden");
          return;
        }
        setState("ready");
      })
      .catch((reason) => {
        if (live) setState(reason);
      });
    return () => {
      live = false;
    };
  }, [admin, navigate]);

  if (state === "loading") return <p className="note">正在确认会话</p>;
  if (state === "forbidden") {
    return (
      <>
        <SessionBar />
        <p className="error">permission_denied：需要管理员</p>
      </>
    );
  }
  if (state !== "ready") {
    return (
      <p className="error">
        {state.code}：{state.message}
      </p>
    );
  }
  return (
    <>
      <SessionBar />
      {children}
    </>
  );
}
