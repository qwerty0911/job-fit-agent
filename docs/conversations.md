# 대화 및 동시성 제어

## 개요

대화 상태는 사용자 단위가 아니라 `conversation_id` 단위로 분리한다. 인증된 사용자는 여러 대화를 가질 수 있으며, 각 대화는 별도의 LangGraph checkpoint thread를 사용한다.

```text
thread_id = conversation_id
```

사용자 UUID는 대화 소유권과 개인 데이터 접근에 사용하고, 대화 UUID는 대화 문맥과 checkpoint 분리에 사용한다.

## API

모든 개인 대화 API는 JWT 인증이 필요하다.

### 대화 생성

```http
POST /conversations
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "title": "백엔드 공고 분석"
}
```

성공하면 `201 Created`와 새 `conversation_id`를 반환한다.

```json
{
  "conversation_id": "conversation-uuid",
  "owner_user_uuid": "user-uuid",
  "title": "백엔드 공고 분석",
  "version": 0,
  "created_at": "2026-10-10T00:00:00Z",
  "updated_at": "2026-10-10T00:00:00Z"
}
```

### 대화 목록 조회

```http
GET /conversations
Authorization: Bearer <access_token>
```

현재 principal이 소유한 대화만 조회하며, `updated_at` 최신순으로 반환한다. 목록 응답에는 대화 메타데이터만 포함하고 전체 메시지나 checkpoint를 포함하지 않는다.

### 대화 단건 조회

```http
GET /conversations/{conversation_id}
Authorization: Bearer <access_token>
```

`conversation_id`와 JWT principal의 사용자 UUID를 함께 조건으로 사용한다. 다른 사용자의 대화이거나 존재하지 않는 대화면 `404 Not Found`를 반환한다.

### 대화 메시지 전송

```http
POST /conversations/{conversation_id}/chat
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "message": "이 공고에서 가장 중요한 요구사항을 알려줘"
}
```

서버는 대화 소유권을 확인한 뒤 `conversation_id`를 LangGraph의 `thread_id`로 사용한다.

## MongoDB 데이터 구조

`conversations` 컬렉션에 대화마다 하나의 문서를 저장한다.

```json
{
  "_id": "conversation-uuid",
  "owner_user_uuid": "user-uuid",
  "title": "백엔드 공고 분석",
  "version": 0,
  "created_at": "2026-10-10T00:00:00Z",
  "updated_at": "2026-10-10T00:00:00Z"
}
```

대화 메타데이터와 전체 메시지·checkpoint를 하나의 MongoDB 문서에 계속 중첩하지 않는다. LangGraph 상태는 checkpoint 저장소에서 `thread_id=conversation_id`로 관리한다.

대화 목록 조회 성능을 위해 다음 인덱스를 사용한다.

```javascript
db.conversations.createIndex({
  owner_user_uuid: 1,
  updated_at: -1
})
```

## 소유권 검증

클라이언트가 보낸 사용자 UUID를 권한 근거로 사용하지 않는다. 모든 대화 API는 검증된 JWT principal의 사용자 UUID를 사용한다.

```text
JWT principal 확인
→ conversation_id와 owner_user_uuid 조회
→ 소유자 일치 시 처리
→ 불일치 또는 미존재 시 404
```

다른 사용자의 대화 존재 여부를 노출하지 않기 위해 소유권 불일치와 미존재를 동일하게 `404 Not Found`로 처리한다.

## 대화별 동시성 제어

같은 대화에 대한 LangGraph 실행은 Redis 분산 락으로 직렬화한다.

```text
lock:conversation:<conversation_id>
```

락 획득에는 Redis `SET NX EX`를 사용한다.

- 락 획득 성공: 채팅 실행
- 락 획득 실패: 다른 요청이 같은 대화를 처리 중이므로 `409 Conflict`
- 처리 완료·실패: 소유자 token을 확인한 뒤 락 해제
- 프로세스 종료: TTL 만료 후 락 자동 해제

락 token은 클라이언트에 반환하지 않는다. 락을 해제할 때는 락을 획득한 요청의 token과 현재 Redis 값을 비교하여 다른 요청의 락을 삭제하지 않도록 한다.

### 충돌 응답

```http
HTTP/1.1 409 Conflict
Retry-After: 1
```

```json
{
  "detail": "대화가 현재 처리 중입니다. 잠시 후 다시 시도해주세요."
}
```

클라이언트는 동일한 메시지를 무한 재시도하지 않고, `Retry-After`를 참고해 제한된 횟수로 재시도한다. 서로 다른 `conversation_id`는 서로 다른 락을 사용하므로 병렬 처리할 수 있다.

## 기존 checkpoint 처리 정책

기존 구현의 `thread_id=user_uuid` checkpoint를 새 `conversation_id` 문서로 자동 이관하지 않는다.

- 배포 후 생성되는 새 대화부터 `thread_id=conversation_id`를 사용한다.
- 기존 사용자 단위 checkpoint는 새 대화 목록에 자동으로 노출하지 않는다.
- 기존 checkpoint의 메시지·검색 상태를 임의의 대화에 승계하지 않는다.
- 필요하면 별도의 검증된 마이그레이션 작업으로만 이관한다.

## 검증 시나리오

- 같은 사용자의 두 대화에서 서로 다른 검색 결과와 선택 공고가 유지된다.
- A 사용자의 토큰으로 B 사용자의 대화를 조회하거나 실행할 수 없다.
- 같은 `conversation_id`에 동시 요청을 보내면 한 요청은 `200`, 다른 요청은 `409`가 된다.
- 서로 다른 `conversation_id`는 동시에 `200`으로 처리된다.
- 두 API 인스턴스가 같은 Redis를 사용할 때도 같은 대화의 락이 공유된다.
- 처리 중인 API 프로세스를 종료해도 락 TTL 만료 후 새 요청이 처리된다.
- 처리 완료 후 Redis의 `lock:conversation:<conversation_id>` key가 삭제된다.

