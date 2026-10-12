from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from resume_job_matcher.application.job_watch_service import (
    SafePublicPageFetcher,
    collect_jobs,
    load_config,
    load_history,
    load_seen,
    save_history,
    save_seen,
    write_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor approved public recruitment pages and write a daily keyword report."
    )
    parser.add_argument("--config", type=Path, required=True, help="Path to job watch JSON config")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report without updating the deduplication state",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="source_ids",
        help="Run only the named source id; repeat the option to select multiple sources",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    if args.source_ids:
        selected = set(args.source_ids)
        known_source_ids = {source.id for source in config.sources}
        unknown = selected - known_source_ids
        if unknown:
            raise ValueError(f"unknown source ids: {', '.join(sorted(unknown))}")
        for source in config.sources:
            source.enabled = source.enabled and source.id in selected
    state_path = config.report_dir / "seen.json"
    history_path = config.report_dir / "history.json"
    previously_seen = load_seen(state_path)
    history = load_history(history_path)
    fetcher = SafePublicPageFetcher()
    registration_errors: list[str] = []
    try:
        for source in config.sources:
            if source.enabled:
                try:
                    fetcher.register_robots(source)
                except (httpx.HTTPError, OSError, RuntimeError, ValueError) as error:
                    source.enabled = False
                    registration_errors.append(f"{source.id} robots: {error}")
        jobs, errors = collect_jobs(
            config,
            fetcher.fetch,
            known_fingerprints=set(history),
        )
        errors = registration_errors + errors
    finally:
        fetcher.close()

    current = {job.fingerprint: job for job in jobs}
    new_fingerprints = set(current) - set(history) - previously_seen
    for fingerprint, job in current.items():
        history.setdefault(fingerprint, job)
    cumulative_jobs = sorted(
        history.values(),
        key=lambda job: (job.score, job.reliability, job.published_at or job.first_seen_at.date()),
        reverse=True,
    )
    markdown_path, csv_path = write_reports(
        config.report_dir,
        cumulative_jobs,
        new_fingerprints,
        errors,
        history_start_date=config.history_start_date,
    )
    if not args.dry_run:
        save_history(history_path, cumulative_jobs)
        save_seen(state_path, previously_seen | set(current))

    print(
        f"matched={len(jobs)} cumulative={len(cumulative_jobs)} "
        f"new={len(new_fingerprints)} errors={len(errors)}"
    )
    print(f"markdown={markdown_path}")
    print(f"csv={csv_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
