import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const documentSubmitDuration = new Trend("document_submit_duration_ms", true);
const embeddingDuration = new Trend("embedding_e2e_duration_ms", true);
const completedJobs = new Counter("embedding_completed_jobs");
const failedJobs = new Counter("embedding_failed_jobs");
const timedOutJobs = new Counter("embedding_timed_out_jobs");

const vus = Number(__ENV.VUS || 5);
const iterations = Number(__ENV.ITERATIONS || 1);
const pollIntervalSeconds = Number(__ENV.POLL_INTERVAL || 1);
const timeoutSeconds = Number(__ENV.JOB_TIMEOUT || 180);

export const options = {
  scenarios: {
    embedding_duration: {
      executor: "per-vu-iterations",
      vus,
      iterations,
      maxDuration: `${timeoutSeconds + 30}s`,
    },
  },
  thresholds: {
    checks: ["rate==1"],
    embedding_e2e_duration_ms: ["p(95)<60000"],
    embedding_failed_jobs: ["count==0"],
    embedding_timed_out_jobs: ["count==0"],
  },
};

function parseJson(response) {
  try {
    return JSON.parse(response.body);
  } catch {
    return null;
  }
}

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:8000";
  const startedAt = Date.now();
  const idempotencyKey =
    `${__ENV.IDEMPOTENCY_PREFIX || "k6-embedding"}-` +
    `${__VU}-${__ITER}-${startedAt}`;

  const submitStartedAt = Date.now();

  const createResponse = http.post(
    `${baseUrl}/profile/documents`,
    JSON.stringify({
      title: `k6 임베딩 시간 측정 ${__VU}-${__ITER}`,
      content:
        "Python, FastAPI, MongoDB, Redis와 비동기 작업 처리 경험을 측정하기 위한 테스트 문서입니다.",
    }),
    {
      headers: {
        Authorization: `Bearer ${__ENV.ACCESS_TOKEN}`,
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
    },
  );

  documentSubmitDuration.add(Date.now() - submitStartedAt);

  const createBody = parseJson(createResponse);
  const createSucceeded = check(createResponse, {
    "document registration returns 202": (response) =>
      response.status === 202,
    "document registration returns job_id": () =>
      Boolean(createBody && createBody.job_id),
  });

  if (!createSucceeded || !createBody?.job_id) {
    failedJobs.add(1);
    return;
  }

  const jobId = createBody.job_id;
  const deadline = Date.now() + timeoutSeconds * 1000;
  let finalStatus = null;

  while (Date.now() < deadline) {
    const statusResponse = http.get(`${baseUrl}/jobs/${jobId}`, {
      headers: {
        Authorization: `Bearer ${__ENV.ACCESS_TOKEN}`,
      },
    });

    const statusBody = parseJson(statusResponse);
    const status = statusBody && statusBody.status;

    if (status === "succeeded" || status === "failed") {
      finalStatus = status;
      break;
    }

    sleep(pollIntervalSeconds);
  }

  if (finalStatus === "succeeded") {
    embeddingDuration.add(Date.now() - startedAt);
    completedJobs.add(1);
    check(finalStatus, {
      "embedding job succeeded": (value) => value === "succeeded",
    });
  } else if (finalStatus === "failed") {
    failedJobs.add(1);
    check(finalStatus, {
      "embedding job succeeded": (value) => value === "succeeded",
    });
  } else {
    timedOutJobs.add(1);
    check(false, {
      "embedding job completed before timeout": (value) => value,
    });
  }
}
