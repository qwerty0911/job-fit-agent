# 문서 버전 관리와 인덱스 정합성

## 목적

이력서 수정 중 새 버전의 Pinecone 인덱싱이 실패하거나 작업 완료 순서가 뒤바뀌면, 검색 결과가 오래된 버전으로 되돌아가거나 삭제된 문서가 다시 노출될 수 있다.

MongoDB를 문서와 작업 상태의 기준 저장소로 사용하고, Pinecone은 MongoDB 상태에서 파생된 검색 인덱스로 취급한다.

## 전체 흐름

```text
문서 등록/수정
  ↓
MongoDB에 현재 문서와 버전별 원문 저장
  ↓
document_jobs에 version을 포함한 인덱싱 작업 저장
  ↓
Worker가 해당 version의 원문을 임베딩
  ↓
Pinecone에 {document_id}:v{version}:chunk:{index} 저장
  ↓
성공한 버전만 active_version으로 전환
```

Worker는 `profile_documents.content`를 직접 읽어 처리하지 않는다. 작업에 지정된 버전의 원문을 `document_versions`에서 읽기 때문에, 수정 요청이 연속으로 들어와도 작업 버전과 원문이 섞이지 않는다.

## MongoDB 구조

### profile_documents

현재 문서의 상태와 검색에 노출할 버전을 저장한다.

```json
{
  "_id": "document_id",
  "user_uuid": "owner_user_uuid",
  "document_type": "resume",
  "title": "현재 이력서 제목",
  "content": "현재 이력서 원문",
  "current_version": 2,
  "active_version": 2,
  "status": "active",
  "vector_store": {
    "provider": "pinecone",
    "version": 2,
    "status": "indexed",
    "id_prefix": "document_id:v2"
  }
}
```

- `current_version`: 마지막으로 생성된 버전
- `active_version`: 검색에 사용할 버전
- `status`: `indexing`, `active`, `failed`, `deleted`
- `active_version`은 인덱싱이 성공하기 전까지 변경하지 않는다.

### document_versions

각 버전의 원문 스냅샷을 보관한다.

```json
{
  "_id": "document_id:v2",
  "document_id": "document_id",
  "owner_user_uuid": "owner_user_uuid",
  "version": 2,
  "title": "수정된 이력서 제목",
  "content": "수정 당시의 원문",
  "index_status": "succeeded"
}
```

`document_id`와 `version` 조합에는 unique 제약을 사용해 같은 버전의 스냅샷이 중복 저장되지 않도록 한다.

### document_jobs

작업은 처리 대상 버전을 함께 저장한다.

```json
{
  "_id": "job_id",
  "job_type": "document_indexing",
  "document_id": "document_id",
  "owner_user_uuid": "owner_user_uuid",
  "version": 2,
  "status": "pending",
  "attempts": 0,
  "max_attempts": 3,
  "lease_until": null,
  "error": null
}
```

## 문서 수정

```http
PUT /profile/documents/{document_id}
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "title": "수정된 이력서",
  "content": "Python, FastAPI, MongoDB 경험이 있습니다."
}
```

수정 요청은 MongoDB의 `current_version`을 원자적으로 증가시킨다.

```text
current_version = 1
  ↓
current_version = 2
  ↓
document_versions에 version 2 원문 저장
  ↓
version 2 인덱싱 작업 생성
```

응답은 임베딩 완료가 아니라 작업 접수를 의미한다.

```json
{
  "document_id": "document_id",
  "job_id": "job_id",
  "version": 2,
  "status": "pending"
}
```

## 활성 버전 전환

새 버전의 Pinecone 저장이 성공한 뒤에만 `active_version`을 갱신한다. 갱신 조건에는 현재 활성 버전보다 큰 버전만 허용한다.

```text
version 3 완료 → active_version = 3
version 2 지연 완료 → active_version은 3 유지
```

따라서 작업 완료 순서가 뒤바뀌어도 검색 대상이 과거 버전으로 회귀하지 않는다.

새 버전 인덱싱이 실패하면 기존 `active_version`을 유지한다.

```text
active_version = 1
version 2 인덱싱 실패
→ active_version = 1 유지
```

## 검색 시 버전 검증

Pinecone에는 여러 버전의 벡터가 남아 있을 수 있으므로, 검색 결과를 그대로 사용하지 않는다.

```text
Pinecone에서 top_k보다 많은 후보 조회
  ↓
MongoDB에서 문서 소유권·status·active_version 조회
  ↓
삭제·실패·비활성 버전 제거
  ↓
Pinecone metadata.version == MongoDB active_version인 결과만 사용
  ↓
최종 top_k개 반환
```

비활성 벡터는 즉시 물리 삭제하지 않아도 검색 근거로 사용되지 않는다. 오래된 벡터는 후속 조정 작업에서 정리할 수 있다.

## 문서 삭제

```http
DELETE /profile/documents/{document_id}
Authorization: Bearer <access-token>
```

삭제는 논리 삭제와 물리 삭제를 분리한다.

```text
1. MongoDB status = deleted
2. 검색 결과에서 즉시 제외
3. document_cleanup 작업 생성
4. Worker가 Pinecone에서 document_id 기준 벡터 삭제
```

Pinecone 벡터는 사용자 namespace 안에서 metadata의 `document_id`를 기준으로 삭제한다. 이 조건은 해당 문서의 모든 버전 벡터에 적용된다.

삭제 작업이 처리 중 종료되면 일반 문서 작업과 동일하게 `lease_until` 만료 후 다시 선점한다.

## 작업 상태와 복구

```text
pending → running → succeeded
                  ↘ failed
```

Worker가 처리 중 종료되면 작업은 `running`으로 남을 수 있다. `lease_until`이 만료되면 다음 Worker가 작업을 다시 선점한다.

정리 작업도 동일한 선점·임대·재시도 흐름을 사용한다.

외부 Pinecone 저장 또는 삭제 성공 직후 프로세스가 종료될 수 있으므로 외부 호출 자체의 exactly-once는 보장하지 않는다. 대신 다음 정책을 사용한다.

- 결정적인 벡터 ID로 같은 버전의 upsert 중복을 줄인다.
- 삭제 작업은 같은 문서 ID 기준으로 반복 실행할 수 있다.
- MongoDB 상태를 기준으로 검색 노출 여부를 결정한다.
- 실패 원인은 `document_jobs.error`에 기록한다.

## 검증 시나리오

- 새 문서 등록 후 `current_version=1`, `active_version=1` 확인
- 문서 수정 후 `current_version=2`와 `document_versions.version=2` 확인
- version 2 성공 후 Pinecone ID가 `document_id:v2:chunk:{index}`인지 확인
- version 2 실패 시 version 1이 계속 검색되는지 확인
- version 3이 먼저 완료되고 version 2가 나중에 완료되어도 `active_version=3`인지 확인
- 삭제 후 MongoDB `status=deleted`와 검색 결과 제외 확인
- cleanup job 처리 후 해당 문서의 모든 버전 벡터 삭제 확인
- cleanup Worker를 `running` 상태에서 종료한 뒤 lease 만료 후 재처리 확인
- 다른 사용자의 문서 ID로 수정·삭제할 때 `404`인지 확인

## 현재 한계와 후속 작업

- MongoDB와 Pinecone을 하나의 트랜잭션으로 묶을 수 없으므로 두 저장소의 단일 원자성은 보장하지 않는다.
- 현재 로컬 작업 전달은 MongoDB polling을 사용한다. AWS 전환 시 SQS 또는 Outbox 기반 Dispatcher가 필요하다.
- 오래된 pending/running 작업, 잔존 벡터, 불일치 상태를 정기적으로 찾는 별도 조정 작업이 필요하다.
- 원문 삭제, 벡터 삭제, 분석 캐시, LangGraph 체크포인트, trace의 보존 기간은 서비스 정책에 맞춰 별도로 정해야 한다.
