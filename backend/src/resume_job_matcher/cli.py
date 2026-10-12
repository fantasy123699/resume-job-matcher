import argparse
import getpass
import sys

from sqlalchemy import select

from resume_job_matcher.application.auth_service import create_invitation
from resume_job_matcher.core.config import get_settings
from resume_job_matcher.core.security import hash_password
from resume_job_matcher.infrastructure.db import SessionLocal
from resume_job_matcher.infrastructure.models import User, UserRole
from resume_job_matcher.infrastructure.skill_repository import sync_seed_skills


def create_admin(email: str) -> None:
    password = getpass.getpass("Admin password (at least 12 characters): ")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    normalized_email = email.strip().lower()
    with SessionLocal.begin() as database_session:
        if database_session.execute(
            select(User).where(User.email == normalized_email)
        ).scalar_one_or_none():
            raise ValueError("This email is already registered")
        database_session.add(
            User(
                email=normalized_email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN.value,
            )
        )


def create_cli_invitation(email: str, max_uses: int, expires_in_days: int) -> str:
    normalized_email = email.strip().lower()
    with SessionLocal.begin() as database_session:
        admin = database_session.execute(
            select(User).where(User.email == normalized_email, User.role == UserRole.ADMIN.value)
        ).scalar_one_or_none()
        if admin is None:
            raise ValueError("An existing administrator is required")
        _, code = create_invitation(
            database_session,
            get_settings(),
            created_by=admin,
            max_uses=max_uses,
            expires_in_days=expires_in_days,
        )
        return code


def sync_skill_aliases() -> int:
    with SessionLocal.begin() as database_session:
        return sync_seed_skills(database_session)


def guard_report(completion_file: str, source_file: str) -> int:
    """Run the fact guard over a saved completion and print what survived.

    This exists so the guard's behaviour can be inspected without a database, a
    network call, or an API key — the acceptance rate is the metric that matters.
    """

    from resume_job_matcher.domain.fact_guard import guard_facts

    with open(completion_file, encoding="utf-8") as handle:
        completion = handle.read()
    with open(source_file, encoding="utf-8") as handle:
        source_lines = {
            f"line:{index}": line.strip()
            for index, line in enumerate(handle.read().splitlines(), start=1)
            if line.strip()
        }

    outcome = guard_facts(completion, source_lines)
    print(f"accepted: {len(outcome.accepted)}")
    print(f"rejected: {len(outcome.rejected)}")
    print(f"acceptance_rate: {outcome.acceptance_rate:.2%}")
    for rejected in outcome.rejected:
        print(f"  dropped [{rejected.reason}] {rejected.statement[:60]}")
    return len(outcome.accepted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume Job Matcher local administration")
    commands = parser.add_subparsers(dest="command", required=True)
    admin_command = commands.add_parser("create-admin", help="Create the initial administrator")
    admin_command.add_argument("--email", required=True)
    invitation_command = commands.add_parser(
        "create-invitation", help="Create an invitation as an admin"
    )
    invitation_command.add_argument("--admin-email", required=True)
    invitation_command.add_argument("--max-uses", type=int, default=1)
    invitation_command.add_argument("--expires-in-days", type=int, default=30)
    commands.add_parser(
        "sync-skill-aliases",
        help="Materialise the bundled skill seed into skill_aliases for inspection",
    )
    guard_command = commands.add_parser(
        "guard-report",
        help="Run the fact guard over a saved completion and report what survived",
    )
    guard_command.add_argument("--completion-file", required=True)
    guard_command.add_argument("--source-file", required=True)
    args = parser.parse_args()

    try:
        if args.command == "guard-report":
            # Deliberately handled before anything touches the database so the guard
            # can be exercised on a laptop with no PostgreSQL running.
            guard_report(args.completion_file, args.source_file)
            return

        if args.command == "create-admin":
            create_admin(args.email)
            print("Administrator created.")
        elif args.command == "sync-skill-aliases":
            created = sync_skill_aliases()
            print(f"Skill aliases synchronised ({created} new rows).")
        else:
            if args.max_uses < 1 or args.expires_in_days < 1:
                raise ValueError("Invitation limits must be positive")
            invitation_code = create_cli_invitation(
                args.admin_email, args.max_uses, args.expires_in_days
            )
            print(f"Invitation code (show once): {invitation_code}")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
