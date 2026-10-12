"""Tests for the fact guard.

The guard is the component that lets the product claim "we never add a fact you did
not write" while still using a model. These tests pin the behaviour that claim rests
on: a fluent, confident, well-formed hallucination is still dropped.
"""

from resume_job_matcher.domain.fact_guard import (
    ALLOWED_CATEGORIES,
    RejectionReason,
    guard_facts,
    normalize_for_matching,
    statement_is_grounded,
)

SOURCE = {
    "line:1": "个人优势",
    "line:2": "熟练使用 Python、C++，遵循编程规范",
    "line:3": "参与大模型数据集建设工作，承担样本标注任务",
    "line:4": "南通大学 本科 通信工程 2023-2027",
}


def test_verbatim_quote_is_accepted_and_anchored_to_its_line() -> None:
    completion = (
        '[{"category":"skill","statement":"熟练使用 Python 和 C++",'
        '"quote":"熟练使用 Python、C++","source_ref":"line:2","confidence":0.9}]'
    )

    outcome = guard_facts(completion, SOURCE)

    assert len(outcome.accepted) == 1
    assert outcome.accepted[0].source_ref == "line:2"
    assert outcome.accepted[0].quote == "熟练使用 Python、C++"
    assert outcome.rejected == []


def test_hallucinated_fact_is_dropped_even_when_confident_and_well_formed() -> None:
    """The core promise: a plausible invention with no source quote never persists."""

    completion = (
        '[{"category":"skill","statement":"精通 Kubernetes 与大规模分布式部署",'
        '"quote":"精通 Kubernetes 与大规模分布式部署","source_ref":"line:2",'
        '"confidence":0.99}]'
    )

    outcome = guard_facts(completion, SOURCE)

    assert outcome.accepted == []
    assert len(outcome.rejected) == 1
    # The declared line exists but does not contain the quote, so the failure is
    # specifically "the text is not in the source", not "the reference is bad".
    assert outcome.rejected[0].reason is RejectionReason.QUOTE_NOT_FOUND


def test_fact_without_a_quote_is_rejected() -> None:
    completion = '[{"category":"skill","statement":"熟悉 Python","quote":""}]'

    outcome = guard_facts(completion, SOURCE)

    assert outcome.accepted == []
    assert outcome.rejected[0].reason is RejectionReason.SCHEMA_MISMATCH


def test_invented_source_reference_falls_back_to_a_full_scan() -> None:
    """A wrong reference must not discard a real quote; the text is the evidence."""

    completion = (
        '[{"category":"education","statement":"南通大学通信工程本科",'
        '"quote":"南通大学 本科 通信工程","source_ref":"page:99,line:99"}]'
    )

    outcome = guard_facts(completion, SOURCE)

    assert len(outcome.accepted) == 1
    assert outcome.accepted[0].source_ref == "line:4"
    assert outcome.rejected == []


def test_unknown_category_is_rejected_so_downstream_queries_stay_typed() -> None:
    completion = (
        '[{"category":"salary_expectation","statement":"期望 4-8K",'
        '"quote":"熟练使用 Python、C++","source_ref":"line:2"}]'
    )

    outcome = guard_facts(completion, SOURCE)

    assert outcome.accepted == []
    assert outcome.rejected[0].reason is RejectionReason.UNKNOWN_CATEGORY
    assert "salary_expectation" not in ALLOWED_CATEGORIES


def test_fenced_json_and_surrounding_prose_are_tolerated() -> None:
    completion = (
        "Here are the facts I found:\n```json\n"
        '[{"category":"skill","statement":"熟练使用 Python","quote":"熟练使用 Python、C++",'
        '"source_ref":"line:2"}]\n```\nLet me know if you need more.'
    )

    outcome = guard_facts(completion, SOURCE)

    assert len(outcome.accepted) == 1


def test_malformed_json_is_reported_rather_than_raising() -> None:
    outcome = guard_facts("I could not find any facts in this resume.", SOURCE)

    assert outcome.accepted == []
    assert outcome.rejected[0].reason is RejectionReason.MALFORMED_JSON
    assert outcome.acceptance_rate == 0.0


def test_duplicate_statements_are_collapsed() -> None:
    completion = (
        '[{"category":"skill","statement":"熟练使用 Python","quote":"熟练使用 Python、C++",'
        '"source_ref":"line:2"},'
        '{"category":"skill","statement":"熟练使用 Python","quote":"熟练使用 Python、C++",'
        '"source_ref":"line:2"}]'
    )

    outcome = guard_facts(completion, SOURCE)

    assert len(outcome.accepted) == 1
    assert outcome.rejected[0].reason is RejectionReason.DUPLICATE


def test_full_width_punctuation_variants_still_match_their_source() -> None:
    """PDF extraction yields full-width punctuation; a byte compare would over-reject."""

    sources = {"line:1": "熟练使用 Python，掌握 RAG 完整流程"}
    completion = (
        '[{"category":"skill","statement":"掌握 RAG","quote":"熟练使用 Python, 掌握 RAG",'
        '"source_ref":"line:1"}]'
    )

    outcome = guard_facts(completion, sources)

    assert len(outcome.accepted) == 1
    # The stored quote stays exactly as the model wrote it, punctuation included.
    assert outcome.accepted[0].quote == "熟练使用 Python, 掌握 RAG"


def test_quote_must_be_contiguous_not_an_assortment_of_source_words() -> None:
    """Guards against a model stitching a plausible sentence from scattered words."""

    sources = {"line:1": "熟悉 Python，了解 Docker"}
    completion = (
        '[{"category":"skill","statement":"熟悉 Docker 和 Python",'
        '"quote":"熟悉 Docker Python","source_ref":"line:1"}]'
    )

    outcome = guard_facts(completion, sources)

    assert outcome.accepted == []
    assert outcome.rejected[0].reason is RejectionReason.QUOTE_NOT_FOUND


def test_normalization_collapses_layout_artifacts() -> None:
    assert normalize_for_matching("  熟练 使用\u00a0Python  ") == "熟练 使用 python"
    assert normalize_for_matching("A\u2014B") == normalize_for_matching("A-B")
    assert normalize_for_matching("Python，掌握") == normalize_for_matching("Python, 掌握")


def test_acceptance_rate_reflects_the_mix() -> None:
    completion = (
        '[{"category":"skill","statement":"熟练使用 Python","quote":"熟练使用 Python、C++",'
        '"source_ref":"line:2"},'
        '{"category":"skill","statement":"精通 Kubernetes","quote":"精通 Kubernetes",'
        '"source_ref":"line:2"}]'
    )

    outcome = guard_facts(completion, SOURCE)

    assert len(outcome.accepted) == 1
    assert len(outcome.rejected) == 1
    assert outcome.acceptance_rate == 0.5


# --- statement grounding: a real quote is not enough ----------------------------
#
# A model can pair a genuine quote with a statement the quote does not support. That
# is exactly the embellishment the product exists to prevent, so the guard refuses it.


def test_an_upgraded_proficiency_verb_is_refused() -> None:
    """The core embellishment: the source says 了解, the statement claims 精通."""

    sources = {"line:1": "了解 Docker 基础"}
    completion = (
        '[{"category":"skill","statement":"精通 Docker","quote":"了解 Docker 基础",'
        '"source_ref":"line:1"}]'
    )

    outcome = guard_facts(completion, sources)

    assert outcome.accepted == []
    assert outcome.rejected[0].reason is RejectionReason.STATEMENT_NOT_GROUNDED


def test_a_real_quote_with_an_invented_duration_is_refused() -> None:
    sources = {"line:1": "熟悉 Python"}
    completion = (
        '[{"category":"experience","statement":"拥有 5 年 Python 架构经验",'
        '"quote":"熟悉 Python","source_ref":"line:1"}]'
    )

    outcome = guard_facts(completion, sources)

    assert outcome.accepted == []
    assert outcome.rejected[0].reason is RejectionReason.STATEMENT_NOT_GROUNDED


def test_a_real_quote_with_an_invented_count_is_refused() -> None:
    sources = {"line:1": "了解 Docker 基础"}
    completion = (
        '[{"category":"achievement","statement":"用 Docker 部署了 200 个微服务",'
        '"quote":"了解 Docker 基础","source_ref":"line:1"}]'
    )

    outcome = guard_facts(completion, sources)

    assert outcome.accepted == []
    assert outcome.rejected[0].reason is RejectionReason.STATEMENT_NOT_GROUNDED


def test_a_quantity_present_in_the_quote_is_allowed() -> None:
    """The check must not reject numbers the source actually states."""

    sources = {"line:1": "具有 3 年 Python 后端开发经验"}
    completion = (
        '[{"category":"experience","statement":"具有 3 年经验",'
        '"quote":"具有 3 年 Python 后端开发经验","source_ref":"line:1"}]'
    )

    outcome = guard_facts(completion, sources)

    assert len(outcome.accepted) == 1


def test_grounding_accepts_a_faithful_restatement() -> None:
    """Legitimate paraphrases that neither add quantities nor upgrade must survive."""

    assert statement_is_grounded("熟悉 Python", "熟悉 Python")
    assert statement_is_grounded("熟练使用 Python 和 FastAPI", "熟练使用 Python、FastAPI")
    assert statement_is_grounded("了解 Docker", "了解 Docker 基础")
    # A weaker claim than the source is always safe.
    assert statement_is_grounded("了解 Python", "熟练使用 Python")


def test_grounding_refuses_a_stronger_claim_than_the_source() -> None:
    assert not statement_is_grounded("熟悉 Python", "了解 Python")
    assert not statement_is_grounded("精通 Python", "熟悉 Python")
    assert not statement_is_grounded("熟练使用 Python", "了解 Python")


def test_grounding_does_not_punish_a_quantity_free_statement() -> None:
    """A statement with no numbers cannot invent one, so it is not blocked on that axis."""

    assert statement_is_grounded("熟悉 Python", "熟悉 Python 3.10")


def test_grounding_is_independent_of_punctuation_normalization() -> None:
    assert statement_is_grounded("熟练使用 Python，掌握 RAG", "熟练使用 Python, 掌握 RAG")
