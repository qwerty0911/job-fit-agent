# Docker 실행 및 라즈베리파이 배포 준비

현재 구성은 FastAPI 백엔드를 컨테이너로 실행합니다. MongoDB, Pinecone, LLM API는 환경변수에 지정한 외부 서비스에 연결합니다. 프론트엔드는 이 저장소에 포함되어 있지 않습니다.

## 1. 준비

- Docker Engine/Desktop 및 Docker Compose v2
- 연결 가능한 MongoDB와 기존 채용 공고 데이터
- LLM 및 임베딩 API 키, Pinecone 인덱스
- 라즈베리파이는 64비트 OS(ARM64)를 기준으로 구성했습니다. `uname -m`이 `aarch64`인지 확인하세요. 32비트 OS는 이번 검증 대상이 아닙니다.

`.env`가 없다면 `.env.example`을 복사하고 값을 입력합니다. 기존 `.env`가 있으면 덮어쓰지 마세요.

```bash
cp .env.example .env
```

`OPENAI_API_KEY`, `EMBEDDING_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `MONGODB_URI`를 설정하세요. `.env`는 Git과 Docker 빌드에서 제외되며 컨테이너 실행 시 주입됩니다.

### MongoDB 주소

| DB 위치 | MONGODB_URI 예시 |
| --- | --- |
| MongoDB Atlas | Atlas에서 제공하는 `mongodb+srv://...` 연결 문자열 |
| Docker를 실행하는 호스트 | `mongodb://host.docker.internal:27017` |
| 별도 서버 | `mongodb://<DB 서버 주소>:27017` |

컨테이너 안의 `localhost`는 API 컨테이너 자신입니다. 기존 `.env`가 `mongodb://localhost:27017`이면 수정해야 합니다. Atlas는 실행 장비의 외부 IP를 네트워크 접근 목록에 허용해야 합니다.

Linux 호스트 MongoDB는 Docker 브리지에서 접근 가능한 주소에 바인딩되어 있어야 합니다. 호스트의 `127.0.0.1`에만 바인딩된 DB는 `host.docker.internal`로 접근할 수 없습니다. DB 인증과 방화벽을 유지하고 DB 포트를 인터넷에 공개하지 마세요.

MongoDB 컨테이너는 포함하지 않았습니다. 라즈베리파이 모델별 MongoDB CPU 지원 여부가 확인되지 않았으므로 기존 DB 또는 Atlas를 사용합니다. API 이미지를 새로 빌드해도 외부 DB 데이터는 유지되며, 채용 공고를 자동으로 생성하거나 이관하지 않습니다.

## 2. 빌드와 실행

```bash
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

정상 응답은 `{"status":"ok","mongodb":"connected"}`입니다. API 문서는 `http://127.0.0.1:8000/docs`에서 확인합니다. `/health`는 MongoDB 연결을 확인하며 LLM/Pinecone 호출 성공까지 보장하지 않습니다. 실제 데이터로 채팅과 문서 검색도 확인하세요.

```bash
# 로그 확인
docker compose logs --tail=100 -f api
# 코드 또는 의존성 변경 반영
docker compose up -d --build --wait --wait-timeout 120
# 환경변수 변경 반영
docker compose up -d --force-recreate --wait --wait-timeout 120
# 중지 및 컨테이너 제거 (외부 DB 데이터는 유지)
docker compose down
```

DB 연결 실패로 시작하지 못하면 `MONGODB_URI`, DB 인증 및 네트워크 설정을 확인합니다. 상태가 `unhealthy`이면 로그를 확인하세요. `restart: unless-stopped`는 프로세스 종료 후 재시작 정책이며, unhealthy 상태만으로 자동 재시작하지는 않습니다.

## 3. 도메인 연결 준비

현재 기본 포트 바인딩은 `127.0.0.1:8000`입니다. 같은 장비에서 실행하는 리버스 프록시가 이 주소로 전달하도록 구성할 수 있습니다. 다른 컨테이너에서 프록시를 실행한다면 동일 Docker 네트워크에 연결하고 `api:8000`으로 전달해야 합니다.

같은 LAN에서 직접 테스트할 때는 `.env`에 `APP_BIND_ADDRESS=0.0.0.0`을 설정하고 컨테이너를 다시 생성한 뒤 `http://<라즈베리파이 IP>:8000/docs`로 접속합니다.

프론트엔드 주소가 정해지면 다음처럼 설정합니다. 여러 주소는 쉼표로 구분하며 끝에 `/`를 붙이지 않습니다.

```dotenv
CORS_ORIGINS=https://portfolio.example.com,http://localhost:5173
```

CORS는 사용자 인증 기능이 아닙니다. 현재 `/login`은 아이디로 UUID를 반환하는 구조이므로 공개 서비스에 필요한 인증과 LLM 호출 제한은 별도 작업입니다.

## 4. ARM64 이미지 및 이후 CI/CD

라즈베리파이에서 직접 `docker compose up -d --build`를 실행하면 호스트 아키텍처로 빌드합니다. 다른 컴퓨터에서 ARM64 이미지를 시험 빌드하려면 Buildx 및 필요한 에뮬레이션 환경을 준비한 뒤 실행합니다.

```bash
docker buildx build --platform linux/arm64 -t mini-pjt-api:arm64 --load .
```

향후 GitHub Actions는 `linux/amd64,linux/arm64` 이미지를 GHCR에 발행하고, 라즈베리파이는 해당 이미지를 받아 실행하는 방식으로 연결할 수 있습니다. 설정 예시는 다음과 같습니다. 실제 저장소와 이미지 태그로 바꿔야 하며 비공개 이미지는 먼저 레지스트리 로그인이 필요합니다.

```dotenv
APP_IMAGE=ghcr.io/<owner>/<repository>:<commit-sha>
```

```bash
docker compose pull api
docker compose up -d --no-build --wait --wait-timeout 120
```

이 단계에서는 GitHub Actions 워크플로, 원격 배포, 도메인 및 HTTPS를 구성하지 않았습니다. 라즈베리파이 접속 방식과 도메인이 정해진 뒤 연결합니다.

## 파일 역할과 의존성 갱신

- `Dockerfile`: Python 3.12 이미지에 의존성과 앱을 설치하고 일반 사용자로 Uvicorn 실행. `/health` 헬스체크 포함.
- `compose.yaml`: 환경변수, 포트, 재시작, 로그 용량 설정.
- `.dockerignore`: 비밀키, 가상환경, 생성 파일을 빌드 대상에서 제외.
- `requirements.txt`: 현재 개발 환경을 기준으로 고정한 직접 의존성.
- `requirements.lock`: 전이 의존성 및 다운로드 해시까지 고정한 설치 목록.
- `requirments.txt`: 기존 오타 파일명을 사용하는 명령의 호환성 유지.

의존성을 변경할 때 `requirements.txt`를 수정한 다음 아래 명령으로 잠금 파일을 갱신하고 이미지를 다시 빌드합니다.

```bash
uv pip compile requirements.txt --python-version 3.12 --universal --generate-hashes --output-file requirements.lock
```

참고: [Docker 멀티 플랫폼 빌드](https://docs.docker.com/build/building/multi-platform/), [Compose 환경변수](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
