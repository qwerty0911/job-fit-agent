# 인증

## 개요

이 서비스는 아이디와 비밀번호로 회원가입·로그인을 처리하고, 로그인 성공 시 짧은 수명의 Access JWT를 발급한다.

- 비밀번호는 Argon2id 해시로 저장한다.
- 비밀번호 원문과 JWT는 로그에 남기지 않는다.
- JWT의 `sub`는 MongoDB `users` 문서의 내부 UUID(`_id`)다.
- Refresh Token은 이 문서의 범위에 포함하지 않는다.

## 회원가입

### 요청

```http
POST /signup
Content-Type: application/json
```

```json
{
  "user_id": "testuser",
  "password": "testpassword123"
}
```

아이디는 정규화한 뒤 중복 여부를 확인한다. 정규화는 Unicode NFKC 적용, 앞뒤 공백 제거, `casefold()` 순서로 처리한다.

비밀번호는 앞뒤 공백을 제거하지 않고 Argon2id로 해시한 뒤 `password_hash`로 저장한다.

### 성공 응답

상태 코드 `201 Created`.

```json
{
  "user_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "testuser",
  "message": "회원가입이 완료되었습니다."
}
```

응답에는 비밀번호 또는 `password_hash`를 포함하지 않는다.

### 오류 응답

- `422 Unprocessable Entity`: 아이디 또는 비밀번호 형식이 유효하지 않음
- `409 Conflict`: 정규화된 아이디가 이미 존재함

## 로그인

### 요청

```http
POST /login
Content-Type: application/json
```

```json
{
  "user_id": "testuser",
  "password": "testpassword123"
}
```

로그인은 사용자를 새로 생성하지 않는다. 정규화된 아이디로 기존 사용자를 조회한 뒤 Argon2id로 비밀번호를 검증한다.

### 성공 응답

상태 코드 `200 OK`.

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user_uuid": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 오류 응답

아이디가 존재하지 않거나 비밀번호가 틀리거나 비밀번호 해시가 없는 경우 모두 동일하게 응답한다.

- `401 Unauthorized`
- 응답 메시지: `아이디 또는 비밀번호가 올바르지 않습니다.`

계정 존재 여부가 외부에 노출되지 않도록 실패 원인을 구분하지 않는다.

## 인증이 필요한 요청

로그인 응답의 `access_token`을 Bearer Token으로 전달한다.

```http
GET /auth/me
Authorization: Bearer <access_token>
```

정상 응답 예시:

```json
{
  "user_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "testuser"
}
```

토큰이 없거나, 위조·만료되었거나, 발급자·대상·필수 claim이 올바르지 않으면 `401 Unauthorized`를 반환한다.

## Access JWT 규칙

서버 설정의 알고리즘과 비밀키로 서명하며, 다음 claim을 포함한다.

| Claim | 의미 |
| --- | --- |
| `sub` | 내부 사용자 UUID |
| `exp` | 만료 시각 |
| `iss` | 토큰 발급자 |
| `aud` | 토큰 대상 API |
| `jti` | 토큰 고유 식별자 |
| `iat` | 발급 시각 |

서버는 다음을 검증한다.

- 허용된 알고리즘인지 확인
- 서명 확인
- `exp` 만료 여부 확인
- 설정된 `iss`와 일치하는지 확인
- 설정된 `aud`와 일치하는지 확인
- `sub`, `exp`, `iss`, `aud`, `jti`가 모두 존재하는지 확인
- `sub`에 해당하는 사용자가 DB에 존재하는지 확인

JWT 비밀키는 환경변수 `JWT_SECRET_KEY`로 주입하며 저장소에 커밋하지 않는다.

## 사용자 데이터 구조

```json
{
  "_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "testuser",
  "user_id_key": "testuser",
  "password_hash": "$argon2id$...",
  "created_at": "2026-10-09T00:00:00Z"
}
```

`user_id`는 표시용 값이고, `user_id_key`는 정규화된 중복 확인·검색용 값이다. `user_id_key`에는 unique index를 적용한다.

## 기존 계정 정책

기존 아이디 기반 로그인으로 생성된 계정 중 `password_hash`가 없는 계정은 로그인할 수 없다.

- 아이디 일치만으로 기존 UUID나 이력서를 자동 승계하지 않는다.
- 검증된 매핑 없이 기존 계정의 비밀번호를 설정하지 않는다.
- 기존 계정 문서는 자동 삭제하지 않는다.
- 비밀번호 재설정 또는 검증된 계정 전환 절차가 마련되기 전까지 해당 계정은 사용 보류 상태로 둔다.

기존 계정 확인:

```javascript
db.users.find(
  { password_hash: { $exists: false } },
  { _id: 1, user_id: 1 }
)
```

## `user_id_key` unique index 마이그레이션

운영 DB에 인덱스를 생성하기 전에 중복 데이터를 점검한다.

```javascript
db.users.aggregate([
  {
    $group: {
      _id: "$user_id_key",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
])
```

중복이 있으면 문서를 자동 삭제하지 않고, 계정 소유자를 확인한 뒤 병합·비활성화·재가입 중 하나의 처리 방안을 결정한다. 중복을 해결한 뒤 다음 unique index를 생성한다.

```javascript
db.users.createIndex(
  { user_id_key: 1 },
  {
    unique: true,
    name: "users_user_id_key_unique"
  }
)
```

새 DB에서도 동일한 인덱스를 생성해야 한다. 동시 회원가입 요청은 애플리케이션의 중복 조회와 DB의 unique constraint를 함께 사용하며, unique constraint 위반은 `409 Conflict`로 변환한다.

## 보안 주의사항

- 비밀번호 원문을 응답·로그·DB에 저장하지 않는다.
- `password_hash`를 응답에 포함하지 않는다.
- JWT 원문을 로그에 남기지 않는다.
- `.env`와 실제 JWT 비밀키를 저장소에 커밋하지 않는다.
- 개인 데이터 API의 소유권 검증은 BE-02 범위에서 별도로 적용한다.
- Refresh Token 수명주기는 BE-03 범위에서 별도로 적용한다.

## 개인 데이터 API와 소유권

개인 데이터 API는 요청 본문이나 경로의 `user_uuid`를 권한 근거로 사용하지 않는다. 사용자 식별자는 검증된 JWT의 `sub`에서 얻은 principal을 사용한다.

| Method | Endpoint | 인증 | 사용자 식별자 |
| --- | --- | --- | --- |
| `POST` | `/chat` | 필요 | JWT principal |
| `GET` | `/profile/me` | 필요 | JWT principal |
| `POST` | `/profile/add_skills` | 필요 | JWT principal |
| `POST` | `/profile/documents` | 필요 | JWT principal |
| `POST` | `/profile/documents/search` | 필요 | JWT principal |
| `GET` | `/postings/me` | 필요 | JWT principal |

다음 API는 인증 없이 사용할 수 있다.

| Method | Endpoint | 목적 |
| --- | --- | --- |
| `GET` | `/health` | 서버·DB 상태 확인 |
| `POST` | `/signup` | 회원가입 |
| `POST` | `/login` | 로그인 및 Access JWT 발급 |

### 요청 형식 변경

개인 데이터 요청에서 클라이언트가 `user_uuid`를 보내지 않는다. 서버가 JWT principal에서 사용자 UUID를 결정한다.

예를 들어 스킬 추가 요청은 다음과 같다.

```http
POST /profile/add_skills
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "skill": "Python"
}
```

문서 생성 요청도 사용자 UUID 없이 보낸다.

```json
{
  "title": "이력서",
  "content": "경력 및 기술 내용"
}
```

서버는 인증된 principal을 다음 경계에 사용한다.

- MongoDB 프로필·문서 조회 및 수정 조건
- 새 문서의 소유자 필드
- Pinecone namespace
- LangGraph thread ID와 실행 context

따라서 A 사용자의 토큰으로 요청하더라도 B 사용자의 UUID를 입력해 B의 데이터를 조회하거나 변경할 수 없다.

## 인증·인가 오류 정책

- `401 Unauthorized`: 토큰이 없거나 유효하지 않음, 만료됨, 발급자·대상·필수 claim이 올바르지 않음
- `404 Not Found`: 인증된 사용자가 접근할 수 없는 개별 리소스이거나 존재 여부를 노출하지 않아야 하는 경우
- `409 Conflict`: 회원가입 시 정규화된 아이디가 이미 존재함
- `422 Unprocessable Entity`: 요청 필드 또는 형식이 유효하지 않음

다른 사용자의 데이터가 존재하는지 외부에 노출하지 않도록 개인 리소스 접근 실패는 필요한 경우 `404`로 처리한다. 인증 실패와 인가 실패의 응답에는 비밀번호, 비밀키, JWT 원문을 포함하지 않는다.

## 소유권 검증 체크리스트

두 개의 테스트 계정 A와 B를 만들어 각각 로그인하고, 발급된 토큰으로 다음을 확인한다.

- A 토큰으로 A 프로필만 조회된다.
- B 토큰으로 B 프로필만 조회된다.
- A 토큰으로 B의 스킬이나 문서를 조회·변경할 수 없다.
- A 토큰으로 문서를 만들면 MongoDB 소유자와 Pinecone namespace가 A로 저장된다.
- B 토큰의 문서 검색 결과에 A의 문서가 포함되지 않는다.
- A와 B의 채팅 실행이 서로의 LangGraph thread 또는 checkpoint를 사용하지 않는다.
- 토큰 없이 개인 데이터 API를 호출하면 `401`이다.
- 요청에 다른 사용자의 UUID를 넣어도 서버는 JWT principal만 사용한다.

새 개인 데이터 API를 추가할 때도 반드시 `get_current_user` 의존성을 적용하고, 클라이언트 입력이 아닌 principal을 소유자로 사용한다.
