import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "10s", target: 5 },
    { duration: "30s", target: 5 },
    { duration: "10s", target: 0 },
  ],
};

export default function () {
  const response = http.get(
    `${__ENV.BASE_URL || "http://localhost:8000"}/health`
  );

  check(response, {
    "status is 200": (res) => res.status === 200,
  });

  sleep(1);
}