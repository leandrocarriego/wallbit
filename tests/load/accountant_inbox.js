// Several accountants working the console at once: inbox, a close's detail and its message.
// Run after month_close_burst (needs computed closes).
import http from "k6/http";
import { check, sleep } from "k6";

const API = __ENV.API_URL || "http://api:8000/api/v1";
const PERIOD = "2026-10";

export const options = {
  scenarios: { accountants: { executor: "constant-vus", vus: 5, duration: "1m" } },
  thresholds: {
    "http_req_duration{page:inbox}": ["p(95)<300"],
    "http_req_duration{page:detail}": ["p(95)<300"],
    "http_req_duration{page:preview}": ["p(95)<300"],
    http_req_failed: ["rate<0.01"],
  },
};

export function setup() {
  const inbox = http.get(`${API}/period-closes?period=${PERIOD}&limit=500`).json();
  if (!inbox.rows.length) throw new Error("No hay cierres: corré antes month_close_burst.");
  return { ids: inbox.rows.map((r) => r.close_id) };
}

export default function (data) {
  const inbox = http.get(`${API}/period-closes?period=${PERIOD}`, { tags: { page: "inbox" } });
  check(inbox, { "inbox 200": (r) => r.status === 200 });
  const id = data.ids[Math.floor(Math.random() * data.ids.length)];
  check(http.get(`${API}/period-closes/${id}`, { tags: { page: "detail" } }), { "detail 200": (r) => r.status === 200 });
  check(http.get(`${API}/period-closes/${id}/message-preview`, { tags: { page: "preview" } }), {
    "preview 200": (r) => r.status === 200,
  });
  sleep(1);
}
