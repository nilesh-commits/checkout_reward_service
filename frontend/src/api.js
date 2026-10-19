// Thin API client. All money is handled server-side in integer cents; the UI only
// displays the `*_display` strings the API returns.

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_TOKEN || "dev-admin-token";

async function request(path, { method = "GET", body, admin = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (admin) headers["X-Admin-Token"] = ADMIN_TOKEN;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    // Surface the structured error code so the UI can show it clearly.
    const err = data?.error || { code: "UNKNOWN", message: res.statusText };
    throw Object.assign(new Error(err.message), { code: err.code, status: res.status });
  }
  return data;
}

export const api = {
  listProducts: () => request("/products"),
  createCart: () => request("/carts", { method: "POST" }),
  getCart: (id) => request(`/carts/${id}`),
  addItem: (id, product_id, quantity) =>
    request(`/carts/${id}/items`, { method: "POST", body: { product_id, quantity } }),
  updateItem: (id, pid, quantity) =>
    request(`/carts/${id}/items/${pid}`, { method: "PATCH", body: { quantity } }),
  removeItem: (id, pid) => request(`/carts/${id}/items/${pid}`, { method: "DELETE" }),
  checkout: (id, coupon_code) =>
    request(`/carts/${id}/checkout`, {
      method: "POST",
      body: { coupon_code: coupon_code || null },
    }),
  getOrder: (id) => request(`/orders/${id}`),
  generateCoupon: () =>
    request("/admin/coupons/generate", { method: "POST", admin: true }),
  report: () => request("/admin/report", { admin: true }),
};
