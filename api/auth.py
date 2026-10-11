from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pymongo.errors import DuplicateKeyError
from redis.exceptions import RedisError

from config import (
    REFRESH_COOKIE_SAMESITE,
    REFRESH_COOKIE_SECURE,
    REFRESH_TOKEN_TTL_SECONDS,
)
from database import get_database
from schema import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from service.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    normalize_user_id,
    verify_password,
)
from service.refresh_token import (
    create_refresh_token,
    revoke_refresh_session,
    rotate_refresh_session,
    store_refresh_session,
)


router = APIRouter(tags=["auth"])


@router.get("/auth/me")
async def get_me_endpoint(current_user=Depends(get_current_user)):
    return {
        "user_uuid": current_user["_id"],
        "user_id": current_user["user_id"],
    }


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup_endpoint(request: SignupRequest):
    db = get_database()
    user_id_key = normalize_user_id(request.user_id)

    if not 2 <= len(user_id_key) <= 20:
        raise HTTPException(status_code=422, detail="아이디는 2~20자로 입력해주세요.")

    try:
        new_user_uuid = str(uuid4())
        await db.users.insert_one({
            "_id": new_user_uuid,
            "user_id": request.user_id,
            "user_id_key": user_id_key,
            "password_hash": hash_password(request.password),
            "created_at": datetime.now(UTC),
        })
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    return SignupResponse(
        user_uuid=new_user_uuid,
        user_id=request.user_id,
        message="회원가입이 완료되었습니다.",
    )


@router.post("/login", response_model=LoginResponse)
async def login_endpoint(request: LoginRequest, response: Response):
    db = get_database()
    user_id_key = normalize_user_id(request.user_id.strip())
    user = await db.users.find_one({"user_id_key": user_id_key})

    if (
        user is None
        or not user.get("password_hash")
        or not verify_password(request.password, user["password_hash"])
    ):
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user["_id"])
    refresh_token, token_id, session_id, family_id = create_refresh_token()
    await store_refresh_session(
        refresh_token=refresh_token,
        token_id=token_id,
        session_id=session_id,
        family_id=family_id,
        user_uuid=user["_id"],
    )
    _set_refresh_cookie(response, refresh_token)

    return LoginResponse(access_token=access_token, token_type="bearer", user_uuid=user["_id"])


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh_access_token_endpoint(
    response: Response,
    refresh_token_value: str | None = Cookie(default=None, alias="refresh_token"),
):
    if refresh_token_value is None:
        raise HTTPException(status_code=401, detail="Refresh Token이 없습니다.")

    try:
        rotated = await rotate_refresh_session(refresh_token_value)
    except (RedisError, RuntimeError):
        raise HTTPException(status_code=503, detail="인증 세션 저장소를 사용할 수 없습니다.")

    if rotated is None:
        raise HTTPException(status_code=401, detail="유효하지 않은 Refresh Token입니다.")

    new_refresh_token, session_data = rotated
    _set_refresh_cookie(response, new_refresh_token)
    return LoginResponse(
        access_token=create_access_token(session_data["user_uuid"]),
        token_type="bearer",
        user_uuid=session_data["user_uuid"],
    )


@router.post("/auth/logout", status_code=204)
async def logout_endpoint(
    response: Response,
    refresh_token_value: str | None = Cookie(default=None, alias="refresh_token"),
):
    if refresh_token_value is not None:
        await revoke_refresh_session(refresh_token_value)
    response.delete_cookie(key="refresh_token", path="/")


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        path="/",
    )
