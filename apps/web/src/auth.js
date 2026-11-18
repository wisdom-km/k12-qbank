/** Session cookie calls. The page sends the CSRF header. It does not choose the teacher. */

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let session = null;
const listeners = new Set();
let unauthenticated = () => {};
let routePath = "/";

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSession() {
  return session;
}

export function notePath(path) {
  routePath = path;
}

export function bindUnauthenticated(handler) {
  unauthenticated = handler;
}

export function dropSession() {
  session = null;
  publish();
}

export async function login(username, secret) {
  const { body } = await request("/api/login", {
    method: "POST",
    body: JSON.stringify({ username, secret }),
  });
  remember(body);
  return body;
}

export async function logout() {
  const result = await request("/api/logout", { method: "POST", body: "{}" });
  dropSession();
  return result;
}

export async function loadSession() {
  try {
    const { body } = await request("/api/session");
    remember(body);
    return body;
  } catch (reason) {
    dropSession();
    if (reason && reason.status === 401) return null;
    throw reason;
  }
}

export async function call(path, options) {
  const { body } = await request(path, options || {});
  return body;
}

export async function callWithId(path, options) {
  return request(path, options || {});
}

async function request(path, options) {
  const method = String((options && options.method) || "GET").toUpperCase();
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...((options && options.headers) || {}),
  };
  if (UNSAFE.has(method) && session && session.csrf_token && path !== "/api/login") {
    headers["X-K12-CSRF"] = session.csrf_token;
  }
  const response = await fetch(path, { ...options, method, headers });
  const text = await response.text();
  const body = readJson(text, response.status);
  if (!response.ok) {
    const error = new Error(body.message || "请求被拒绝");
    error.code = body.code || "refused";
    error.status = response.status;
    error.request_id = body.request_id || response.headers.get("X-Request-Id") || "";
    error.body = body;
    if (response.status === 401 && path !== "/api/login" && routePath !== "/login") {
      dropSession();
      unauthenticated();
    }
    throw error;
  }
  return {
    body,
    requestId: response.headers.get("X-Request-Id") || "",
  };
}

function readJson(text, status) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (reason) {
    const error = new Error("响应不是 JSON");
    error.code = "refused";
    error.status = status;
    error.cause = reason;
    throw error;
  }
}

function remember(body) {
  session = body;
  publish();
}

function publish() {
  for (const listener of listeners) listener();
}
