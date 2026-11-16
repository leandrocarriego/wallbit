// Day-1 burst: start the close for every active client and wait until all are computed.
// Requires the volume seed: `make seed-volume n=2000`.
import http from "k6/http";
import { check, sleep } from "k6";
import encoding from "k6/encoding";
import { Trend } from "k6/metrics";

const API = __ENV.API_URL || "http://api:8000/api/v1";
const RABBIT = __ENV.RABBIT_URL || "http://rabbitmq:15672";
const PERIOD = "2026-10";
const burst = new Trend("close_burst_seconds", false);

export const options = {
  scenarios: { burst: { executor: "shared-iterations", vus: 1, iterations: 1, maxDuration: "15m" } },
  thresholds: {
    close_burst_seconds: ["max<600"], // 100% computed in under 10 minutes
    checks: ["rate==1"],
  },
};

const progress = () => http.get(`${API}/period-closes/progress?period=${PERIOD}`).json();

export function setup() {
  const p = progress();
  if (p.total > 0) throw new Error("El período ya arrancó: corré `make seed-volume` antes.");
}

export default function () {
  const started = Date.now();
  const res = http.post(`${API}/demo/day-1`, null, { headers: { "X-Actor": "k6" } });
  check(res, { "day 1 accepted": (r) => r.status === 200 });

  let p = progress();
  while (!(p.total > 0 && p.computed === p.total) && Date.now() - started < 14 * 60 * 1000) {
    sleep(2);
    p = progress();
  }
  const seconds = (Date.now() - started) / 1000;
  burst.add(seconds);

  const auth = { headers: { Authorization: `Basic ${encoding.b64encode("wallbit:wallbit")}` } };
  const dlq = http.get(`${RABBIT}/api/queues/%2F/dead_letter`, auth).json();
  check(p, { "every close computed": (x) => x.total > 0 && x.computed === x.total });
  check(dlq, { "dead letter queue is empty": (q) => q.messages === 0 });
  console.log(`${p.total} cierres en ${seconds.toFixed(1)} s · ${JSON.stringify(p.by_status)} · DLQ ${dlq.messages}`);
}
