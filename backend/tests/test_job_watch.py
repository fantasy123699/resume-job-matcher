from datetime import UTC, date, datetime
from pathlib import Path

from resume_job_matcher.application.job_watch_service import (
    SourceConfig,
    WatchConfig,
    canonicalize_url,
    collect_jobs,
    extract_candidate_links,
    find_published_date,
    listing_urls_for_source,
    load_history,
    match_job,
    save_history,
    write_reports,
)


def source() -> SourceConfig:
    return SourceConfig(
        id="official_example",
        name="示例企业招聘官网",
        owner="示例企业",
        source_type="official_company",
        reliability=5,
        listing_urls=["https://careers.example.com/campus"],
        allowed_hosts=["careers.example.com"],
        link_url_pattern=r"/jobs/",
        robots_url="https://careers.example.com/robots.txt",
        usage_note="合成测试来源",
        reviewed_at=date(2026, 8, 26),
    )


def config(tmp_path: Path) -> WatchConfig:
    return WatchConfig(
        include_keywords=["Python", "后端", "Java"],
        campus_keywords=["2027届", "校园招聘"],
        exclude_keywords=["社招"],
        min_score=3,
        history_start_date=date(2026, 8, 1),
        report_dir=tmp_path,
        sources=[source()],
    )


def test_extracts_only_registered_matching_links() -> None:
    html = """
    <a href="/jobs/backend?utm_source=test">2027届 Python 后端工程师</a>
    <a href="https://evil.example/jobs/1">外部链接</a>
    <a href="/about">关于我们</a>
    """

    links = extract_candidate_links(html, "https://careers.example.com/campus", source())

    assert [(link.title, link.url) for link in links] == [
        ("2027届 Python 后端工程师", "https://careers.example.com/jobs/backend")
    ]


def test_matching_requires_campus_and_rejects_excluded_jobs(tmp_path: Path) -> None:
    watch_config = config(tmp_path)

    matched = match_job(
        "2027届 Python 后端工程师",
        "负责服务端开发，校园招聘岗位。",
        watch_config,
    )

    assert matched == (6, ("python", "后端"))
    assert match_job("Python 后端工程师", "五年以上社招岗位", watch_config) is None
    assert match_job(
        "Python 后端工程师",
        "负责数据库服务开发",
        watch_config,
        campus_scope=True,
    ) == (6, ("python", "后端"))


def test_collects_deduplicates_and_writes_daily_reports(tmp_path: Path) -> None:
    pages = {
        "https://careers.example.com/campus": """
            <a href="/jobs/backend">2027届 Python 后端工程师</a>
            <a href="/jobs/backend?utm_source=duplicate">重复链接</a>
            <a href="/jobs/sales">2027届销售</a>
        """,
        "https://careers.example.com/jobs/backend": """
            <main><p>校园招聘，负责 Python、数据库和后端服务开发。</p>
            <time>2026-08-25</time></main>
        """,
        "https://careers.example.com/jobs/sales": "<main>校园招聘，负责客户销售。</main>",
    }

    def fetch(url: str, _: tuple[str, ...], __: float) -> str:
        return pages[url]

    jobs, errors = collect_jobs(
        config(tmp_path),
        fetch,
        now=datetime(2026, 8, 26, tzinfo=UTC),
    )

    assert errors == []
    assert len(jobs) == 1
    assert jobs[0].published_at == date(2026, 8, 25)
    assert jobs[0].matched_keywords == ("python", "后端")

    markdown_path, csv_path = write_reports(
        tmp_path,
        jobs,
        {jobs[0].fingerprint},
        [],
        report_date=date(2026, 8, 26),
    )
    assert "2027届 Python 后端工程师" in markdown_path.read_text(encoding="utf-8")
    assert csv_path.read_text(encoding="utf-8-sig").startswith("is_new,title,url")


def test_canonicalization_and_date_extraction() -> None:
    assert (
        canonicalize_url(
            "https://Careers.Example.com/jobs/1/?utm_campaign=fall&from=home&id=7#apply"
        )
        == "https://careers.example.com/jobs/1?id=7"
    )
    assert find_published_date("发布时间：2026年8月25日，截止时间：2026-09-30") == date(2026, 8, 25)
    assert find_published_date("25 2026.08") == date(2026, 8, 25)
    assert find_published_date("08.25") == date(2026, 8, 25)
    assert find_published_date("Aug 24, 2026") == date(2026, 8, 24)


def test_extracts_listing_date_and_expands_pagination() -> None:
    paged_source = source().model_copy(
        update={
            "item_selector": ".content li",
            "link_selector": ".title1 a[href]",
            "listing_date_selector": ".date",
            "pagination_url_template": "https://careers.example.com/campus/p/{page}.html",
            "max_listing_pages": 3,
        }
    )
    html = """
    <div class="content"><ul><li>
      <div class="date"><span>25</span><span>2026.08</span></div>
      <div class="title1"><a href="/jobs/backend">Java开发工程师</a></div>
    </li></ul></div>
    """

    links = extract_candidate_links(html, "https://careers.example.com/campus", paged_source)

    assert links[0].published_at == date(2026, 8, 25)
    assert listing_urls_for_source(paged_source) == [
        "https://careers.example.com/campus",
        "https://careers.example.com/campus/p/2.html",
        "https://careers.example.com/campus/p/3.html",
    ]


def test_history_round_trip(tmp_path: Path) -> None:
    pages = {
        "https://careers.example.com/campus": (
            '<a href="/jobs/backend">2027届 Python 后端工程师</a>'
        ),
        "https://careers.example.com/jobs/backend": (
            "<main>校园招聘，Python 后端开发，发布时间 2026-08-03</main>"
        ),
    }
    jobs, _ = collect_jobs(
        config(tmp_path),
        lambda url, _hosts, _interval: pages[url],
        now=datetime(2026, 8, 26, tzinfo=UTC),
    )
    history_path = tmp_path / "history.json"

    save_history(history_path, jobs)
    loaded = load_history(history_path)

    assert list(loaded.values()) == jobs


def test_known_history_link_skips_repeated_detail_fetch(tmp_path: Path) -> None:
    pages = {
        "https://careers.example.com/campus": (
            '<a href="/jobs/backend">2027届 Python 后端工程师</a>'
        ),
        "https://careers.example.com/jobs/backend": (
            "<main>校园招聘，Python 后端开发，发布时间 2026-08-03</main>"
        ),
    }
    fetched: list[str] = []

    def fetch(url: str, _hosts: tuple[str, ...], _interval: float) -> str:
        fetched.append(url)
        return pages[url]

    first_jobs, _ = collect_jobs(config(tmp_path), fetch, now=datetime(2026, 8, 26, tzinfo=UTC))
    fetched.clear()
    second_jobs, _ = collect_jobs(
        config(tmp_path),
        fetch,
        now=datetime(2026, 8, 26, tzinfo=UTC),
        known_fingerprints={first_jobs[0].fingerprint},
    )

    assert second_jobs == []
    assert fetched == ["https://careers.example.com/campus"]
