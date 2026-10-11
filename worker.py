import asyncio
import logging

from database import connect_to_mongodb, close_mongodb_connection, get_database
from datetime import UTC, datetime

from service.document_job_service import process_document_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 2


async def get_next_available_job() -> dict | None:
    db = get_database()
    now = datetime.now(UTC)

    return await db.document_jobs.find_one(
        {
            "$or": [
                {
                    "status": "pending",
                },
                {
                    "status": "running",
                    "lease_until": {
                        "$lte": now,
                    },
                },
            ],
            "$expr": {
                "$lt": ["$attempts", "$max_attempts"],
            },
        },
        sort=[("created_at", 1)],
    )

async def worker_loop() -> None:
    while True:
        job = await get_next_available_job()

        if job is None:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        job_id = job["_id"]
        logger.info("문서 작업 처리 시작: %s", job_id)

        try:
            await process_document_job(job_id)
            logger.info("문서 작업 처리 완료: %s", job_id)
        except Exception:
            logger.exception("문서 작업 처리 실패: %s", job_id)


async def main() -> None:
    await connect_to_mongodb()

    try:
        await worker_loop()
    finally:
        await close_mongodb_connection()


if __name__ == "__main__":
    asyncio.run(main())