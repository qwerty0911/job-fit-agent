# 문서 등록 멱등성

## 목적

문서 등록 요청의 응답이 유실되면 클라이언트는 같은 요청을 재전송할 수 있다. 요청마다 새로운 문서와 작업을 생성하면 이력서와 임베딩 작업이 중복되므로, 문서 등록 API에 `Idempotency-Key`를 적용한다.

멱등성은 같은 사용자가 같은 작업에 같은 키와 같은 요청 내용을 재전송했을 때 기존 결과를 반환하도록 보장한다.

## API 사용법

```http
POST /profile/documents
Authorization: Bearer <access-token>
Idempotency-Key: resume-request-001
Content-Type: application/json
```

```json
{
  "title": "이력서",
  "content": "Python과 FastAPI를 사용한 프로젝트 경험이 있습니다."
}
```

`Idempotency-Key`는 필수이며 1~255자의 문자열이다. 키는 불투명한 식별자로 취급하고 앞뒤 공백만 제거한다.

## 요청 처리 정책

요청 식별 범위는 다음 세 필드의 조합이다.

```text
owner_user_uuid + job_type + idempotency_key
```

### 같은 키·같은 요청 내용

기존 작업의 `document_id`, `job_id`, 현재 상태를 그대로 반환한다. 새로운 문서나 작업을 만들지 않는다.

```text
HTTP 202
기존 document_id
기존 job_id
```

### 같은 키·다른 요청 내용

요청 내용의 정규화 해시가 기존 작업의 해시와 다르면 충돌로 처리한다.

```text
HTTP 409 Conflict
```

### 다른 사용자·같은 키

사용자 UUID가 식별 범위에 포함되므로 서로 독립적인 문서와 작업을 생성한다.

## 요청 해시

현재 요청 해시는 `title`과 `content`의 앞뒤 공백을 제거하고 JSON 키를 정렬한 뒤 SHA-256으로 생성한다.

```text
normalized title/content
→ canonical JSON
→ SHA-256
→ request_hash
```

비밀번호, 토큰, 문서 원문 전체를 로그에 남기지 않으며 `request_hash`만 작업 기록에 저장한다.

## MongoDB 제약

`document_jobs` 컬렉션에는 다음 복합 unique index를 사용한다.

```text
owner_user_uuid: 1
job_type: 1
idempotency_key: 1
```

기존 멱등성 필드가 없는 작업을 보호하기 위해 다음 partial filter를 사용한다.

```json
{
  "owner_user_uuid": { "$exists": true },
  "job_type": { "$exists": true },
  "idempotency_key": { "$exists": true }
}
```

단순 선조회만으로는 동시 요청을 막을 수 없으므로, 선조회와 MongoDB unique 제약을 함께 사용한다. 동시 요청에서 unique 제약 위반이 발생하면 경쟁 요청은 기존 작업을 다시 조회해 기존 결과를 반환해야 한다.

## 작업 재전달과 벡터 중복

Worker가 같은 작업을 다시 전달받아도 `succeeded` 작업은 다시 처리하지 않는다. 작업이 실제로 실행되는 경우에도 Pinecone 벡터 ID는 다음 규칙을 재사용한다.

```text
{document_id}:v{version}:chunk:{chunk_index}
```

따라서 같은 문서·버전의 재처리는 동일한 벡터 ID에 upsert되며, 새로운 벡터 ID를 계속 생성하지 않는다.

## 키 보관과 재요청

현재 키는 `document_jobs` 작업 기록과 함께 보관한다. 작업 기록을 삭제하거나 별도의 보관 기간을 적용하기 전까지 같은 키는 기존 결과를 재사용한다.

키 보관 기간이 만료된 뒤 같은 키를 사용하면 새로운 요청으로 처리될 수 있으므로, 클라이언트는 재시도 기간 동안 같은 키를 유지하고 새로운 작업에는 새로운 키를 사용해야 한다.

처리 중인 작업에 같은 요청이 다시 들어오면 새로운 작업을 만들지 않고 기존 `job_id`와 현재 상태를 반환한다.

## 검증 시나리오

- 같은 사용자·같은 키·같은 payload를 동시에 요청한다.
  - `profile_documents` 1개
  - `document_jobs` 1개
  - 두 응답의 `document_id`와 `job_id` 동일
- 같은 키로 다른 payload를 요청한다.
  - `409 Conflict`
- 다른 사용자가 같은 키를 사용한다.
  - 사용자별 문서·작업이 각각 생성
- 완료된 작업을 다시 Worker에 전달한다.
  - 새로운 문서·작업·벡터가 생성되지 않음
- Worker를 처리 중 종료한 뒤 같은 작업을 다시 실행한다.
  - 임대 만료 후 재처리

## exactly-once 한계

MongoDB의 unique 제약과 작업 선점으로 애플리케이션 작업의 중복 생성을 줄일 수 있지만, 임베딩 API와 Pinecone 같은 외부 호출 자체의 exactly-once 실행은 보장할 수 없다.

외부 호출 성공 직후 Worker가 종료되면 같은 작업이 재전달될 수 있다. 이 경우 외부 호출이 두 번 발생할 수 있으며 비용이 중복될 수 있다. Pinecone 저장은 결정적인 벡터 ID를 사용해 최종 데이터가 중복 레코드로 쌓이지 않도록 한다.

문서 생성, 멱등성 기록, 작업 생성 사이의 장애 구간은 MongoDB transaction 또는 별도 Outbox/복구 상태 전이로 강화할 수 있다.
