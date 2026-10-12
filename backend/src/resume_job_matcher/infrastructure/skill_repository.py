"""Database extension of the bundled skill dictionary.

The bundled seed is always unioned in, so this module only ever *adds*
knowledge: an operator can insert new terminology or recategorise an existing
skill without a code change, and improving the seed still takes effect on the
next load.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.domain.skill_dictionary import (
    DEFAULT_SKILL_DICTIONARY,
    SEED_SKILLS,
    SkillDictionary,
    SkillEntry,
)
from resume_job_matcher.infrastructure.models import SkillAlias

SEED_SOURCE = "seed"
APPROVED_STATUS = "approved"


def load_skill_dictionary(database_session: Session) -> SkillDictionary:
    """Return the seed dictionary unioned with every approved alias row."""

    rows = database_session.execute(
        select(SkillAlias).where(SkillAlias.status == APPROVED_STATUS)
    ).scalars()
    declared_categories: dict[str, str] = {}
    declared_aliases: dict[str, list[str]] = {}
    for row in rows:
        declared_categories.setdefault(row.canonical_name, row.category)
        aliases = declared_aliases.setdefault(row.canonical_name, [])
        if row.alias != row.canonical_name and row.alias not in aliases:
            aliases.append(row.alias)

    overrides = [
        SkillEntry(
            canonical_name=canonical_name,
            category=declared_categories[canonical_name],
            aliases=tuple(declared_aliases[canonical_name]),
        )
        for canonical_name in declared_categories
    ]
    return DEFAULT_SKILL_DICTIONARY.extended_with(overrides)


def sync_seed_skills(database_session: Session) -> int:
    """Materialise the bundled seed into ``skill_aliases`` and return rows added.

    Idempotent: re-running only inserts pairs that are not present yet, so it is
    safe after upgrading the bundled seed.
    """

    existing = {
        (row.canonical_name, row.alias)
        for row in database_session.execute(select(SkillAlias)).scalars()
    }
    created = 0
    for entry in SEED_SKILLS:
        for term in entry.all_terms:
            if (entry.canonical_name, term) in existing:
                continue
            database_session.add(
                SkillAlias(
                    canonical_name=entry.canonical_name,
                    alias=term,
                    category=entry.category,
                    source=SEED_SOURCE,
                    status=APPROVED_STATUS,
                )
            )
            existing.add((entry.canonical_name, term))
            created += 1
    return created
