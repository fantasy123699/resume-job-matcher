import logging
import signal
import time

from resume_job_matcher.application.account_deletion_service import process_due_account_deletions
from resume_job_matcher.application.agent_run_service import advance_created_agent_runs
from resume_job_matcher.application.document_export_service import cleanup_expired_exports
from resume_job_matcher.core.config import get_settings
from resume_job_matcher.infrastructure.db import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_running = True


def _stop(_: int, __: object) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    settings = get_settings()
    next_export_cleanup = 0.0
    next_account_deletion_cleanup = 0.0
    logger.info("Worker started; task polling will be added with the durable task table.")

    while _running:
        with SessionLocal() as database_session:
            advanced_count = advance_created_agent_runs(database_session)
        if advanced_count:
            logger.info("Advanced %s agent runs to an approval checkpoint", advanced_count)
        if time.monotonic() >= next_export_cleanup:
            with SessionLocal() as database_session:
                removed_count = cleanup_expired_exports(database_session, settings)
            if removed_count:
                logger.info("Removed %s expired document exports", removed_count)
            next_export_cleanup = time.monotonic() + 3600
        if time.monotonic() >= next_account_deletion_cleanup:
            with SessionLocal() as database_session:
                removed_count = process_due_account_deletions(database_session, settings)
            if removed_count:
                logger.info("Deleted %s due accounts", removed_count)
            next_account_deletion_cleanup = time.monotonic() + 3600
        time.sleep(5)

    logger.info("Worker stopped cleanly.")


if __name__ == "__main__":
    main()
