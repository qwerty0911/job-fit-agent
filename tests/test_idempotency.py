from service.idempotency import create_request_hash


def test_request_hash_normalizes_whitespace_and_detects_changes():
    first_hash = create_request_hash(
        title=" 이력서 ",
        content=" Python과 FastAPI 경험이 있습니다. ",
    )
    same_request_hash = create_request_hash(
        title="이력서",
        content="Python과 FastAPI 경험이 있습니다.",
    )
    different_request_hash = create_request_hash(
        title="이력서",
        content="Java와 Spring 경험이 있습니다.",
    )

    assert first_hash == same_request_hash
    assert first_hash != different_request_hash
