from resume_job_matcher.application.job_description_service import (
    parse_job_requirements,
)
from resume_job_matcher.domain.requirement_patterns import (
    classify_clause,
    detect_section,
    split_clauses,
)


def necessity_of(content: str) -> dict[str, str]:
    return {
        requirement.value.name: requirement.requirement_type
        for requirement in parse_job_requirements(content)
    }


def test_section_header_on_its_own_line_sets_necessity_for_following_lines() -> None:
    # The original line-scanning implementation reported these as mandatory
    # because the requirement lines themselves contain no bonus marker.
    content = "\n".join(
        [
            "任职要求",
            "熟悉 Python",
            "加分项",
            "熟悉 Kubernetes",
            "熟悉 Docker",
        ]
    )
    assert necessity_of(content) == {
        "Python": "required",
        "Kubernetes": "bonus",
        "Docker": "bonus",
    }


def test_inline_section_header_is_detected_and_stripped() -> None:
    signal = detect_section("任职要求：熟悉 Python、FastAPI 和 PostgreSQL")
    assert signal is not None
    assert signal.necessity == "required"
    assert signal.header == "任职要求"
    assert signal.remainder == "熟悉 Python、FastAPI 和 PostgreSQL"


def test_benefits_section_produces_no_requirements() -> None:
    content = "\n".join(
        [
            "任职要求：熟悉 Python",
            "我们提供：有竞争力的薪资、Python 与 Kubernetes 培训",
        ]
    )
    signal = detect_section("我们提供：有竞争力的薪资、Python 与 Kubernetes 培训")
    assert signal is not None
    assert signal.necessity is None
    assert necessity_of(content) == {"Python": "required"}


def test_clauses_within_one_line_carry_independent_necessity() -> None:
    content = "任职要求：熟悉 Python，有 Kubernetes 证书者优先，了解 Redis"
    assert necessity_of(content) == {
        "Python": "required",
        "Kubernetes": "bonus",
        "Redis": "required",
    }


def test_explicit_bonus_marker_outranks_the_required_section() -> None:
    classification = classify_clause("熟悉 Kubernetes 者优先", "required")
    assert classification.necessity == "bonus"
    assert classification.matched_marker == "优先"


def test_clause_categories_are_classified() -> None:
    assert classify_clause("本科及以上学历", "required").category == "education"
    assert classify_clause("3 年以上后端开发经验", "required").category == "experience"
    assert classify_clause("具备良好的沟通能力", "required").category == "soft_skill"
    assert classify_clause("熟悉 Python", "required").category == "skill"


def test_split_clauses_ignores_enumeration_commas_within_a_skill_list() -> None:
    assert split_clauses("熟悉 Python、FastAPI 和 PostgreSQL，具备工程实践能力。") == [
        "熟悉 Python、FastAPI 和 PostgreSQL",
        "具备工程实践能力",
    ]


def test_first_mention_wins_when_a_skill_repeats_across_clauses() -> None:
    content = "任职要求：熟悉 Kubernetes。加分项：有 Kubernetes 认证者优先。"
    assert necessity_of(content) == {"Kubernetes": "required"}


def test_parsed_requirement_keeps_clause_level_evidence() -> None:
    content = "任职要求：熟悉 Python，熟悉 Redis 者优先"
    parsed = parse_job_requirements(content)
    assert [(item.value.name, item.requirement_type, item.source_text) for item in parsed] == [
        ("Python", "required", "熟悉 Python"),
        ("Redis", "bonus", "熟悉 Redis 者优先"),
    ]
    assert {item.source_location for item in parsed} == {"line:1"}
