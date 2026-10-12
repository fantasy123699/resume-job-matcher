from resume_job_matcher.domain.skill_dictionary import (
    DEFAULT_SKILL_DICTIONARY,
    SEED_SKILLS,
    SkillDictionary,
    SkillEntry,
)


def names_in(text: str) -> set[str]:
    return {mention.name for mention in DEFAULT_SKILL_DICTIONARY.find_mentions(text)}


def test_seed_covers_the_original_dictionary_and_is_categorised() -> None:
    names = set(DEFAULT_SKILL_DICTIONARY.canonical_names)
    # Every skill the first hardcoded dictionary knew about must survive.
    assert {
        "Python",
        "Java",
        "Go",
        "C++",
        "C#",
        "Rust",
        "JavaScript",
        "TypeScript",
        "Node.js",
        "React",
        "Vue",
        "Next.js",
        "FastAPI",
        "Django",
        "Flask",
        "Spring Boot",
        "MySQL",
        "PostgreSQL",
        "Redis",
        "MongoDB",
        "Docker",
        "Kubernetes",
        "Linux",
        "Git",
        "AWS",
        "阿里云",
    } <= names
    # The dictionary is materially larger than the 26 entries it replaced.
    assert len(DEFAULT_SKILL_DICTIONARY.canonical_names) >= 180
    assert DEFAULT_SKILL_DICTIONARY.category_of("Kubernetes") == "云原生与运维"
    assert DEFAULT_SKILL_DICTIONARY.category_of("PyTorch") == "人工智能"
    assert len({entry.category for entry in SEED_SKILLS}) >= 10


def test_word_boundaries_prevent_substring_false_positives() -> None:
    assert names_in("精通 JavaScript") == {"JavaScript"}
    assert names_in("熟悉 Java") == {"Java"}
    # PostgreSQL must not be reported as SQL.
    assert names_in("PostgreSQL") == {"PostgreSQL"}
    # Longest term wins, so Spring Boot does not also report Spring.
    assert names_in("Spring Boot 微服务") == {"Spring Boot", "Microservices"}


def test_ambiguous_aliases_do_not_match_english_prose() -> None:
    # A bare "Go" is also a common English word, so prose is rejected.
    assert names_in("We go to market quickly") == set()
    assert names_in("Go to market") == set()
    # ...while a skill-list usage is still detected.
    assert names_in("Go、Python") == {"Go", "Python"}
    assert names_in("熟悉 Golang 开发") == {"Go"}


def test_aliases_and_case_folding_resolve_to_canonical_names() -> None:
    assert names_in("k8s 与 K8S 集群") == {"Kubernetes"}
    assert names_in("掌握 springboot") == {"Spring Boot"}
    assert names_in("熟悉 vue3 和 ts") == {"Vue", "TypeScript"}
    assert names_in("阿里云上的 oss") == {"阿里云"}
    assert names_in("使用 pytorch 训练模型") == {"PyTorch"}


def test_mentions_are_reported_once_in_order_of_first_appearance() -> None:
    mentions = DEFAULT_SKILL_DICTIONARY.find_mentions("Redis、Python、Redis、Kafka")
    assert [mention.name for mention in mentions] == ["Redis", "Python", "Kafka"]


def test_mention_records_the_surface_form_that_triggered_it() -> None:
    mentions = DEFAULT_SKILL_DICTIONARY.find_mentions("熟悉 K8s")
    assert [(mention.name, mention.source_text) for mention in mentions] == [("Kubernetes", "K8s")]


def test_extended_with_unions_aliases_and_allows_recategorisation() -> None:
    base = SkillDictionary(
        [SkillEntry(canonical_name="Kubernetes", category="云原生与运维", aliases=("k8s",))]
    )
    extended = base.extended_with(
        [
            SkillEntry(
                canonical_name="Kubernetes",
                category="容器编排",
                aliases=("kube",),
            ),
            SkillEntry(canonical_name="内部框架", category="自研", aliases=("inhouse",)),
        ]
    )
    names = {mention.name for mention in extended.find_mentions("k8s kube inhouse")}
    assert names == {"Kubernetes", "内部框架"}
    # Seed aliases survive the union and the override wins on category.
    assert extended.category_of("Kubernetes") == "容器编排"
    assert set(extended.canonical_names) == {"Kubernetes", "内部框架"}


def test_dictionary_ignores_repeated_canonical_names_deterministically() -> None:
    dictionary = SkillDictionary(
        [
            SkillEntry(canonical_name="Redis", category="数据库", aliases=("redis缓存",)),
            SkillEntry(canonical_name="Redis", category="重复定义", aliases=("another",)),
        ]
    )
    assert dictionary.canonical_names == ("Redis",)
    assert dictionary.category_of("Redis") == "数据库"
