# 부하·동시성·복구 테스트

이 디렉터리는 k6를 이용해 문서 등록 멱등성, 대화 동시성 제어, 서로 다른 대화의 병렬 처리와 문서 작업 복구를 검증한다.

## 준비

API를 실행하고 테스트에 사용할 유효한 Access Token을 준비한다.

```bash
export BASE_URL=http://localhost:8000
export ACCESS_TOKEN="<유효한 Access JWT>"
```

저장소 루트에서 k6 테스트를 실행한다.

```bash
k6 version
```

토큰을 파일이나 저장소에 커밋하지 않는다. 이미 노출된 토큰은 폐기하고 새로 발급한다.

## 1. Health 부하

5개 VU까지 증가시킨 뒤 30초 동안 `/health`를 호출한다.

```bash
k6 run tests/load/health.js
```

확인할 항목은 `status is 200` 체크, 오류율, 요청 지연시간, 서버·MongoDB·Redis 리소스 사용량이다.

## 2. 문서 등록 멱등성

### 같은 키·같은 요청

같은 사용자와 같은 `Idempotency-Key`로 여러 요청을 보내도 문서와 작업은 각각 하나만 만들어져야 한다. 현재 `document_idempotency.js`는 VU별로 서로 다른 키를 사용하므로 워커 복구용 작업 생성에 사용한다. 같은 키 멱등성 테스트를 할 때는 헤더를 다음처럼 바꾼다.

```javascript
"Idempotency-Key": __ENV.IDEMPOTENCY_KEY,
```

그리고 실행한다.

```bash
export IDEMPOTENCY_KEY="k6-idempotency-$(date +%s)"
export VUS=20
k6 run tests/load/document_idempotency.js
```

테스트 후 MongoDB에서 해당 키의 작업 수를 확인한다.

```javascript
db.document_jobs.countDocuments({
  job_type: "document_indexing",
  owner_user_uuid: "<사용자 UUID>",
  idempotency_key: "<IDEMPOTENCY_KEY>"
})
```

기대 결과는 작업 1개, 문서 1개다. 응답이 모두 `202`이고 모든 응답의 `document_id`, `job_id`가 같은지도 확인한다.

같은 키를 유지한 채 `title` 또는 `content`를 바꿔 다시 요청하면 `409 Conflict`가 반환되어야 하며 새 문서나 작업을 만들면 안 된다.

### 유니크 인덱스 확인

MongoDB Shell 또는 Atlas의 MongoDB Shell에서 실행한다.

```javascript
db.document_jobs.getIndexes()
```

다음 복합 인덱스에 `unique: true`가 있어야 한다.

```javascript
db.document_jobs.createIndex(
  { job_type: 1, idempotency_key: 1, owner_user_uuid: 1 },
  { unique: true, name: "uniq_document_job_idempotency" }
)
```

기존 중복 데이터가 있으면 유니크 인덱스 생성이 실패하므로 테스트 DB에서 중복을 정리한 뒤 인덱스를 생성한다. 운영 DB에서 무차별 삭제하지 않는다.

## 3. 같은 대화의 동시 요청

하나의 대화에 동시에 3개의 메시지를 보내고 대화별 락이 중복 실행을 막는지 확인한다.

```bash
export CONVERSATION_ID="<같은 대화 ID>"
export VUS=3
k6 run tests/load/conversation-concurrency.js
```

기대 결과는 요청 1개가 `200`, 나머지가 정책에 따라 `409 Conflict`가 되는 것이다. 상태와 체크포인트도 깨지지 않아야 한다.

`409`는 이 테스트에서 예상된 비즈니스 응답이다. 스크립트의 `check`는 정상적인 충돌 결과로 집계하지만, k6 기본 `http_req_failed` 지표에서는 실패로 보일 수 있으므로 `200/409` 카운터와 함께 해석한다.

## 4. 서로 다른 대화의 병렬 요청

서로 다른 대화에는 동시에 요청해도 서로의 락에 영향을 주지 않아야 한다.

```bash
export CONVERSATION_ID_A="<대화 A ID>"
export CONVERSATION_ID_B="<대화 B ID>"
k6 run tests/load/conversation-parallel.js
```

기대 결과는 두 요청 모두 `200`이며 대화 A와 B의 상태·검색 결과·체크포인트가 섞이지 않는 것이다.

## 5. 워커 복구 테스트

### 작업 만들기

워커를 먼저 중지해 작업이 즉시 처리되지 않게 한다. 현재 `document_idempotency.js`는 VU별로 `worker-recovery-test-1`, `worker-recovery-test-2`와 같은 키를 사용한다.

```bash
export VUS=10
k6 run tests/load/document_idempotency.js
```

MongoDB에서 작업 수를 확인한다.

```javascript
db.document_jobs.countDocuments({
  status: "pending",
  idempotency_key: { $regex: "^worker-recovery-test-" }
})
```

### 만료된 running 작업으로 변환

크래시 후 복구를 재현하려면 테스트 DB의 `pending` 작업을 만료된 `running` 작업으로 바꾼다.

```javascript
db.document_jobs.updateMany(
  {
    status: "pending",
    idempotency_key: { $regex: "^worker-recovery-test-" }
  },
  {
    $set: {
      status: "running",
      lease_until: new Date(Date.now() - 1000),
      updated_at: new Date()
    }
  }
)
```

회수 대상이 만료됐는지 확인한다.

```javascript
db.document_jobs.countDocuments({
  status: "running",
  idempotency_key: { $regex: "^worker-recovery-test-" },
  lease_until: { $lte: new Date() }
})
```

이제 워커를 시작한다. 워커는 만료된 `running` 작업을 원자적으로 선점해 다시 처리해야 한다.

```bash
python3 worker.py
```

처리 후 결과를 확인한다.

```javascript
db.document_jobs.aggregate([
  { $match: { idempotency_key: { $regex: "^worker-recovery-test-" } } },
  { $group: { _id: "$status", count: { $sum: 1 } } }
])
```

기대 결과는 모든 작업이 `succeeded`가 되고, 각 작업의 `attempts`가 재선점 횟수를 반영하는 것이다. 동일 작업이 중복 문서나 중복 벡터를 만들지 않는지도 함께 확인한다.

## 결과 기록

raw 로그 전체를 보관할 필요는 없다. 포트폴리오나 이슈 검증에는 다음 값이면 충분하다.

| 테스트 | 기록할 값 |
| --- | --- |
| 멱등성 | 동시 요청 수, `202` 응답 수, 고유 문서 수, 고유 작업 수 |
| 같은 대화 동시성 | 총 요청 수, `200` 수, `409` 수, 상태 일관성 |
| 다른 대화 병렬성 | 동시 요청 수, 성공 수, 대화별 결과 분리 여부 |
| 워커 복구 | 주입한 작업 수, 만료 작업 수, 복구 성공 수, 최종 실패 수 |

테스트 날짜, 커밋 SHA, API 포트, MongoDB DB 이름, Pinecone 인덱스/네임스페이스도 함께 기록하면 이전 버전과 비교하기 쉽다. API 키, Access Token, Refresh Token, 비밀번호와 같은 비밀값은 결과에 남기지 않는다.

## HTML 리포트

k6 웹 대시보드 리포트를 저장하려면 저장소 루트에서 실행한다.

```bash
mkdir -p reports
K6_WEB_DASHBOARD=true \
K6_WEB_DASHBOARD_OPEN=false \
K6_WEB_DASHBOARD_PERIOD=1s \
K6_WEB_DASHBOARD_EXPORT="$PWD/reports/health.html" \
k6 run tests/load/health.js
```

멱등성·대화 테스트에서 `409`가 정상 결과인 경우에는 HTML의 기본 실패율만으로 합격 여부를 판단하지 말고 스크립트의 `check`, 커스텀 카운터, MongoDB 결과를 함께 기록한다.

## 주의사항

- 실제 운영 DB에서 삭제·상태 변경 쿼리를 실행하지 않는다.
- 임베딩과 LLM 호출이 포함된 테스트는 호출량과 비용을 고려해 VU 수를 작게 시작한다.
- `pending` 작업을 만드는 것과 실제 프로세스 강제 종료 후 lease 회수는 서로 다른 시나리오다.
- 외부 Pinecone 호출은 네트워크 재시도에 따라 완전한 exactly-once를 보장하지 않을 수 있으므로 최종 상태와 벡터 ID 중복 여부를 함께 확인한다.
