import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const unexpectedStatus = new Counter("unexpected_status");

// export const options = {
//   scenarios: {
//     same_key_registration: {
//       executor: "per-vu-iterations",
//       vus: Number(__ENV.VUS || 20),
//       iterations: 1,
//       maxDuration: "30s",
//     },
//   },

//   thresholds: {
//     http_req_failed: ["rate==0"],
//     checks: ["rate==1"],
//     unexpected_status: ["count==0"],
//   },
// };

// 하나만 등록
export const options = {
  scenarios: {
    create_documents: {
      executor: "per-vu-iterations",
      vus: 200,
      iterations: 1,
      maxDuration: "30s",
    },
  },
};

export default function () {
  const response = http.post(
    `${__ENV.BASE_URL}/profile/documents`,
    JSON.stringify({
      title: "k6 멱등성 테스트",
      content: "Python과 FastAPI 경험이 있습니다. 그리고 멱등성 테스트를 하는중입니다.",
    }),
    {
      headers: {
        Authorization: `Bearer ${__ENV.ACCESS_TOKEN}`,
        //"Idempotency-Key": __ENV.IDEMPOTENCY_KEY,
        "Idempotency-Key": `worker-recovery-test-${__VU}`,
        "Content-Type": "application/json",
      },
    },
  );

  const isExpectedStatus = response.status === 202;

  if (!isExpectedStatus) {
    unexpectedStatus.add(1);
  }

  check(response, {
    "status is 202": (res) => res.status === 202,
    "response has document_id": (res) => {
      try {
        return Boolean(JSON.parse(res.body).document_id);
      } catch {
        return false;
      }
    },
    "response has job_id": (res) => {
      try {
        return Boolean(JSON.parse(res.body).job_id);
      } catch {
        return false;
      }
    },
  });
}