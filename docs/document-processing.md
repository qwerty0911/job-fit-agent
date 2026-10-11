# 비동기 이력서 문서 처리

## 목적

이력서 등록 요청에서 텍스트 분할, 임베딩 생성, Pinecone 저장까지 동기 처리하면 HTTP 응답이 오래 걸린다. 따라서 API는 이력서와 작업 정보를 MongoDB에 저장한 뒤 `202 Accepted`와 `job_id`를 반환하고, 별도 Worker가 임베딩 작업을 수행한다.

## 처리 흐름

```text
POST /profile/documents
  ↓
profile_documents에 이력서 저장
document_jobs에 pending 작업 저장
  ↓
202 Accepted + document_id + job_id 반환
  ↓
로컬 Worker가 작업 조회
  ↓
pending → running
  ↓
이력서 조회 → 텍스트 분할 → 임베딩 생성 → Pinecone 저장
  ↓
succeeded / failed 상태 갱신
```

## API

### 이력서 등록

```http
POST /profile/documents
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "title": "이력서",
  "content": "Python과 FastAPI를 사용한 프로젝트 경험이 있습니다."
}
```

응답은 작업 접수만 완료되었다는 의미의 `202 Accepted`이다.

```json
{
  "document_id": "65f...",
  "job_id": "4d43a9b8-cd1c-48fc-8ecd-5dac200e08a1",
  "status": "pending"
}
```

### 작업 상태 조회

```http
GET /jobs/{job_id}
Authorization: Bearer <access-token>
```

응답 예시:

```json
{
  "job_id": "4d43a9b8-cd1c-48fc-8ecd-5dac200e08a1",
  "document_id": "65f...",
  "status": "succeeded",
  "attempts": 1,
  "max_attempts": 3,
  "error": null,
  "created_at": "2026-10-11T10:00:00Z",
  "updated_at": "2026-10-11T10:00:12Z"
}
```

다른 사용자의 `job_id`는 존재 여부를 노출하지 않도록 `404`로 응답한다.

## MongoDB 저장 구조

`profile_documents`에는 이력서와 벡터 저장 상태를 기록한다.

```json
{
  "_id": "document_id",
  "user_uuid": "owner_user_uuid",
  "document_type": "resume",
  "title": "이력서",
  "content": "이력서 원문",
  "vector_store": {
    "provider": "pinecone",
    "version": 1,
    "status": "pending"
  }
}
```

`document_jobs`에는 후속 처리 작업을 기록한다.

```json
{
  "_id": "job_id",
  "job_type": "document_indexing",
  "document_id": "document_id",
  "owner_user_uuid": "owner_user_uuid",
  "status": "pending",
  "attempts": 0,
  "max_attempts": 3,
  "error": null,
  "lease_until": null
}
```

작업 상태는 다음 순서로 변경된다.

```text
pending → running → succeeded
                  ↘ failed
```

## Worker와 작업 회수

현재 로컬 Worker는 2초마다 MongoDB에서 다음 작업을 조회한다.

- `status = pending`
- 또는 `status = running`이고 `lease_until`이 현재 시각보다 이전인 작업

작업을 가져갈 때 MongoDB의 원자적 `find_one_and_update`로 `pending → running`을 변경한다. `attempts`가 `max_attempts` 이상이면 다시 가져가지 않는다.

현재 `DOCUMENT_JOB_LEASE_SECONDS` 기본값은 60초다. `lease_until`은 작업 생성 시점이 아니라 Worker가 작업을 선점한 시점에 설정된다.

Worker가 처리 중 종료되면 작업은 `running`으로 남을 수 있다. 임대 시간이 만료된 뒤 다른 Worker가 해당 작업을 다시 선점해 처리한다.

## AWS SQS 전환 계획

현재 로컬에서는 Worker가 MongoDB를 polling한다. AWS 배포 시에는 SQS를 작업 전달 계층으로 사용한다.

```text
API
  → MongoDB에 작업 저장
  → Dispatcher가 SQS에 job_id 전송
  → Worker가 SQS에서 job_id 수신
  → MongoDB에서 이력서 조회 및 처리
  → 성공 시 SQS 메시지 삭제
```

SQS는 Worker가 아니라 메시지 전달·대기열 역할을 한다. MongoDB는 작업 상태와 결과 조회를 위한 원본 저장소로 유지한다.

MongoDB 저장 후 SQS 전송이 실패할 수 있으므로, 운영 전환 시 미전송 작업을 다시 SQS로 보내는 Dispatcher 또는 Outbox 복구 로직이 필요하다.

## 현재 한계와 후속 작업

현재 구현은 기본적인 작업 선점과 임대 만료 후 회수까지 지원한다. 다음 항목은 후속 개선 사항으로 둔다.

- 처리 중 `lease_until`을 연장하는 heartbeat
- 오래된 Worker가 새 Worker의 결과를 덮어쓰지 않도록 하는 lease token/fencing
- 제한된 backoff 재시도와 DLQ
- SQS Dispatcher 및 큐 송신 실패 복구
- Worker graceful shutdown

현재 임대 시간은 60초이며, 정상적인 문서 처리 시간이 이를 초과하지 않는다는 전제를 둔다. 장시간 처리 보호가 필요한 운영 환경에서는 heartbeat와 fencing을 추가해야 한다.

## 검증 시나리오

- 이력서 등록 응답이 `202`이고 `job_id`를 포함하는지 확인
- 등록 직후 작업 상태가 `pending`인지 확인
- Worker 처리 후 작업이 `succeeded`, 문서의 벡터 상태가 `indexed`인지 확인
- 임베딩 실패 시 작업이 `failed`가 되고 `error`가 기록되는지 확인
- Worker 종료 후 `lease_until` 만료 작업이 재처리되는지 확인
- 다른 사용자의 `job_id` 조회가 `404`인지 확인
