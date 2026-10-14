import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const successCount = new Counter("chat_success");
const conflictCount = new Counter("chat_conflict");
const unexpectedCount = new Counter("chat_unexpected");

export const options = {
  scenarios: {
    same_conversation: {
      executor: "per-vu-iterations",
      vus: Number(__ENV.VUS || 3),
      iterations: 1,
      maxDuration: "60s",
    },
  },
};

export default function () {
  const response = http.post(
    `${__ENV.BASE_URL}/conversations/${__ENV.CONVERSATION_ID}/chat`,
    JSON.stringify({
      message: `동시성 테스트 요청 ${__VU}`,
    }),
    {
      headers: {
        Authorization: `Bearer ${__ENV.ACCESS_TOKEN}`,
        "Content-Type": "application/json",
      },
    },
  );

  if (response.status >= 200 && response.status < 300) {
    successCount.add(1);
  } else if (response.status === 409) {
    conflictCount.add(1);
  } else {
    unexpectedCount.add(1);
  }

  check(response, {
    "status is expected": (res) =>
      res.status >= 200 && res.status < 300 || res.status === 409,
  });
}