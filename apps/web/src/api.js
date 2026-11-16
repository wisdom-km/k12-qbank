export async function call(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    ...options,
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const error = new Error(body.message || "请求被拒绝");
    error.code = body.code || "refused";
    error.body = body;
    throw error;
  }
  return body;
}
