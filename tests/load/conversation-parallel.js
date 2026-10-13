import http from "k6/http";
import { check } from "k6";

http.setResponseCallback(
  http.expectedStatuses(200)
);

export const options = {
  scenarios: {
    different_conversations: {
      executor: "per-vu-iterations",
      vus: 2,
      iterations: 1,
      maxDuration: "60s",
    },
  },
};

export default function () {
  const conversationId =
    __VU === 1
      ? __ENV.CONVERSATION_ID_A
      : __ENV.CONVERSATION_ID_B;

  const response = http.post(
    `${__ENV.BASE_URL}/conversations/${conversationId}/chat`,
    JSON.stringify({
      message: `서로 다른 대화 병렬 처리 테스트 ${__VU}`,
    }),
    {
      headers: {
        Authorization: `Bearer ${__ENV.ACCESS_TOKEN}`,
        "Content-Type": "application/json",
      },
    },
  );

  check(response, {
    "status is 200": (res) => res.status === 200,
  });
}