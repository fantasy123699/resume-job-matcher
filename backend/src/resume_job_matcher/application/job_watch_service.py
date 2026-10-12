from __future__ import annotations

import csv
import hashlib
import ipaddress
import json
import re
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from pydantic import BaseModel, Field, field_validator, model_validator

USER_AGENT = "ResumeJobMatcher-JobWatch/0.1 (+local personal job search)"
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = {"from", "source", "spm", "track", "tracking"}
DATE_PATTERN = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?!\d)")
DAY_YEAR_MONTH_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s+(20\d{2})[./年](\d{1,2})(?!\d)")
# A posting usually carries both a publication date and a deadline, and the
# deadline is the later of the two. This marks the date the page presents as the
# publication or update time, so the deadline is not mistaken for it.
PUBLISH_MARKER_PATTERN = re.compile(
    r"发布|更新时间|更新日期|posted|published|updated",
    re.IGNORECASE,
)
MONTH_DAY_PATTERN = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?!\d)")
ENGLISH_MONTH_DATE_PATTERN = re.compile(
    r"(?<![A-Za-z])([A-Za-z]{3,9})\s+(\d{1,2}),\s*(20\d{2})(?!\d)"
)
ENGLISH_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
SPACE_PATTERN = re.compile(r"\s+")


class SourceConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    owner: str = Field(min_length=1, max_length=100)
    source_type: Literal["official_government", "official_university", "official_company"]
    reliability: int = Field(ge=1, le=5)
    campus_scope: bool = False
    listing_urls: list[str] = Field(min_length=1)
    pagination_url_template: str | None = None
    max_listing_pages: int = Field(default=1, ge=1, le=100)
    allowed_hosts: list[str] = Field(min_length=1)
    item_selector: str | None = None
    link_selector: str = "a[href]"
    link_url_pattern: str = ".*"
    listing_date_selector: str | None = None
    detail_content_selector: str = "body"
    match_from_listing_only: bool = False
    max_detail_pages: int = Field(default=30, ge=1, le=100)
    request_interval_seconds: float = Field(default=1.5, ge=1.0, le=60.0)
    robots_url: str
    terms_url: str | None = None
    usage_note: str = Field(min_length=1, max_length=500)
    reviewed_at: date
    enabled: bool = True

    @field_validator("listing_urls", "robots_url")
    @classmethod
    def require_https(cls, value: list[str] | str) -> list[str] | str:
        urls = value if isinstance(value, list) else [value]
        for url in urls:
            if urlsplit(url).scheme != "https":
                raise ValueError("job watch only accepts HTTPS sources")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_hosts(cls, hosts: list[str]) -> list[str]:
        return [host.strip().lower().rstrip(".") for host in hosts]

    @model_validator(mode="after")
    def validate_registered_hosts(self) -> SourceConfig:
        urls = [*self.listing_urls, self.robots_url]
        if self.pagination_url_template:
            urls.append(self.pagination_url_template.format(page=2))
        for url in urls:
            if (urlsplit(url).hostname or "").lower() not in self.allowed_hosts:
                raise ValueError(f"URL host is not registered in allowed_hosts: {url}")
        if self.max_listing_pages > 1 and not self.pagination_url_template:
            raise ValueError("pagination_url_template is required for multiple listing pages")
        return self


class WatchConfig(BaseModel):
    include_keywords: list[str] = Field(min_length=1)
    campus_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    min_score: int = Field(default=3, ge=1, le=100)
    history_start_date: date
    max_age_days: int = Field(default=60, ge=1, le=365)
    report_dir: Path = Path("data/job_watch")
    sources: list[SourceConfig] = Field(min_length=1)

    @field_validator("include_keywords", "campus_keywords", "exclude_keywords")
    @classmethod
    def normalize_keywords(cls, keywords: list[str]) -> list[str]:
        normalized = [keyword.strip().lower() for keyword in keywords if keyword.strip()]
        return list(dict.fromkeys(normalized))


@dataclass(frozen=True)
class CandidateLink:
    title: str
    url: str
    published_at: date | None = None


@dataclass(frozen=True)
class JobResult:
    fingerprint: str
    title: str
    url: str
    source_id: str
    source_name: str
    source_type: str
    reliability: int
    published_at: date | None
    matched_keywords: tuple[str, ...]
    score: int
    first_seen_at: datetime


FetchText = Callable[[str, tuple[str, ...], float], str]


def fetch_with_retry(
    fetch_text: Callable[..., str],
    url: str,
    allowed_hosts: tuple[str, ...],
    interval_seconds: float,
    *,
    attempts: int = 3,
    fetch_kwargs: dict[str, object] | None = None,
) -> str:
    kwargs = fetch_kwargs or {}
    for attempt in range(1, attempts + 1):
        try:
            return fetch_text(url, allowed_hosts, interval_seconds, **kwargs)
        except (httpx.TransportError, OSError):
            if attempt == attempts:
                raise
            time.sleep(float(attempt))
    raise RuntimeError("unreachable retry state")


class SafePublicPageFetcher:
    def __init__(self, *, max_response_bytes: int = 2_000_000) -> None:
        self.max_response_bytes = max_response_bytes
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request_at: dict[str, float] = {}
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=False,
            timeout=httpx.Timeout(30.0, connect=5.0),
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def register_robots(self, source: SourceConfig) -> None:
        try:
            robots = fetch_with_retry(
                self.fetch,
                source.robots_url,
                tuple(source.allowed_hosts),
                source.request_interval_seconds,
                fetch_kwargs={"check_robots": False},
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code not in {404, 410}:
                raise
            robots = "User-agent: *\nDisallow:"
        parser = RobotFileParser()
        parser.set_url(source.robots_url)
        parser.parse(robots.splitlines())
        for host in source.allowed_hosts:
            self._robots[host] = parser

    def fetch(
        self,
        url: str,
        allowed_hosts: tuple[str, ...],
        interval_seconds: float,
        *,
        check_robots: bool = True,
        redirects_remaining: int = 3,
    ) -> str:
        safe_url = validate_public_url(url, allowed_hosts)
        host = (urlsplit(safe_url).hostname or "").lower()
        if check_robots:
            parser = self._robots.get(host)
            if parser is None:
                raise RuntimeError(f"robots.txt has not been registered for {host}")
            if not parser.can_fetch(USER_AGENT, safe_url):
                raise PermissionError(f"robots.txt does not allow fetching {safe_url}")

        last_request = self._last_request_at.get(host)
        if last_request is not None:
            time.sleep(max(0.0, interval_seconds - (time.monotonic() - last_request)))

        with self._client.stream("GET", safe_url) as response:
            self._last_request_at[host] = time.monotonic()
            if 300 <= response.status_code < 400:
                if redirects_remaining <= 0:
                    raise RuntimeError(f"too many redirects from {safe_url}")
                redirect = response.headers.get("location")
                if not redirect:
                    raise RuntimeError(f"redirect without Location from {safe_url}")
                redirected_url = urljoin(safe_url, redirect)
                validate_public_url(redirected_url, allowed_hosts)
                return self.fetch(
                    redirected_url,
                    allowed_hosts,
                    interval_seconds,
                    check_robots=check_robots,
                    redirects_remaining=redirects_remaining - 1,
                )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/" not in content_type and "html" not in content_type:
                raise ValueError(f"unsupported content type from {safe_url}: {content_type}")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > self.max_response_bytes:
                    raise ValueError(f"response is larger than {self.max_response_bytes} bytes")
            return bytes(body).decode(response.encoding or "utf-8", errors="replace")


def load_config(path: Path) -> WatchConfig:
    return WatchConfig.model_validate_json(path.read_text(encoding="utf-8"))


def validate_public_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise ValueError(f"only credential-free HTTPS URLs are allowed: {url}")
    if host not in allowed_hosts:
        raise ValueError(f"host is not in this source's allowlist: {host}")
    port = parts.port or 443
    addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    if not addresses:
        raise ValueError(f"host did not resolve: {host}")
    for address in addresses:
        parsed_address = ipaddress.ip_address(address)
        if not parsed_address.is_global:
            raise ValueError(f"host resolves to a non-public address: {host}")
    return urlunsplit(("https", parts.netloc, parts.path or "/", parts.query, ""))


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_NAMES
        and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), "")
    )


def extract_candidate_links(
    html: str, listing_url: str, source: SourceConfig
) -> list[CandidateLink]:
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(source.link_url_pattern)
    found: dict[str, CandidateLink] = {}
    items = soup.select(source.item_selector) if source.item_selector else []
    anchors: list[tuple[Tag, Tag | None]] = []
    if items:
        for item in items:
            anchor = item.select_one(source.link_selector)
            if anchor is not None:
                anchors.append((anchor, item))
    else:
        anchors = [(anchor, None) for anchor in soup.select(source.link_selector)]

    for candidate_anchor, candidate_item in anchors:
        href = candidate_anchor.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        absolute_url = canonicalize_url(urljoin(listing_url, href.strip()))
        host = (urlsplit(absolute_url).hostname or "").lower()
        if host not in source.allowed_hosts or not pattern.search(absolute_url):
            continue
        title = candidate_anchor.get_text(" ", strip=True)
        if not title:
            title_attribute = candidate_anchor.get("title")
            title = title_attribute if isinstance(title_attribute, str) else ""
        title = clean_text(title)
        if not title:
            continue
        published_at = None
        if candidate_item is not None and source.listing_date_selector:
            date_element = candidate_item.select_one(source.listing_date_selector)
            if date_element is not None:
                published_at = find_published_date(date_element.get_text(" ", strip=True))
        found.setdefault(
            absolute_url,
            CandidateLink(title=title, url=absolute_url, published_at=published_at),
        )
    return list(found.values())


def extract_page_text(html: str, selector: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    selected = soup.select(selector)
    if selected:
        return clean_text(" ".join(element.get_text(" ", strip=True) for element in selected))
    return clean_text(soup.get_text(" ", strip=True))


def clean_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", value).strip()


def find_published_date(text: str) -> date | None:
    """Find the publication date, preferring the one a publish marker points at.

    A posting usually carries a publication date *and* a deadline, and the
    deadline is the later of the two. Returning the latest date therefore picked
    the deadline instead of the date the page published. The latest date is kept
    as the fallback because it avoids stale boilerplate such as a copyright
    year, but when the text names a publication or update marker, the first date
    at or after that marker wins.
    """

    candidates: list[tuple[int, date]] = []
    for match in DATE_PATTERN.finditer(text):
        try:
            candidates.append((match.start(), date(int(match[1]), int(match[2]), int(match[3]))))
        except ValueError:
            continue
    for match in DAY_YEAR_MONTH_PATTERN.finditer(text):
        try:
            candidates.append((match.start(), date(int(match[2]), int(match[3]), int(match[1]))))
        except ValueError:
            continue
    current_year = datetime.now(UTC).year
    for match in MONTH_DAY_PATTERN.finditer(text):
        try:
            candidates.append((match.start(), date(current_year, int(match[1]), int(match[2]))))
        except ValueError:
            continue
    for match in ENGLISH_MONTH_DATE_PATTERN.finditer(text):
        month = ENGLISH_MONTHS.get(match[1].lower())
        if month is None:
            continue
        try:
            candidates.append((match.start(), date(int(match[3]), month, int(match[2]))))
        except ValueError:
            continue

    today = datetime.now(UTC).date()
    plausible = [(position, parsed) for position, parsed in candidates if parsed <= today]
    if not plausible:
        return None

    marker = PUBLISH_MARKER_PATTERN.search(text)
    if marker is not None:
        after_marker = [item for item in plausible if item[0] >= marker.start()]
        if after_marker:
            return min(after_marker, key=lambda item: item[0])[1]
    return max(parsed for _, parsed in plausible)


def listing_urls_for_source(source: SourceConfig) -> list[str]:
    urls = list(source.listing_urls)
    if source.pagination_url_template:
        urls.extend(
            source.pagination_url_template.format(page=page)
            for page in range(2, source.max_listing_pages + 1)
        )
    return urls


def match_job(
    title: str,
    detail_text: str,
    config: WatchConfig,
    *,
    campus_scope: bool = False,
) -> tuple[int, tuple[str, ...]] | None:
    normalized_title = title.lower()
    normalized_detail = detail_text.lower()
    if any(
        keyword in f"{normalized_title} {normalized_detail}" for keyword in config.exclude_keywords
    ):
        return None
    if (
        not campus_scope
        and config.campus_keywords
        and not any(
            keyword in f"{normalized_title} {normalized_detail}"
            for keyword in config.campus_keywords
        )
    ):
        return None
    matched = tuple(
        keyword
        for keyword in config.include_keywords
        if keyword in normalized_title or keyword in normalized_detail
    )
    if not matched:
        return None
    score = sum(3 if keyword in normalized_title else 1 for keyword in matched)
    return (score, matched) if score >= config.min_score else None


def title_has_campus_marker(title: str, config: WatchConfig) -> bool:
    normalized_title = title.lower()
    return any(keyword in normalized_title for keyword in config.campus_keywords)


def build_job_result(
    candidate: CandidateLink,
    source: SourceConfig,
    match: tuple[int, tuple[str, ...]],
    detail_text: str,
    collected_at: datetime,
    config: WatchConfig,
) -> JobResult | None:
    score, matched_keywords = match
    published_at = candidate.published_at or find_published_date(detail_text)
    if published_at is not None and published_at < config.history_start_date:
        return None
    if published_at is not None:
        age = (collected_at.date() - published_at).days
        if age > config.max_age_days:
            return None
    fingerprint = hashlib.sha256(candidate.url.encode()).hexdigest()
    return JobResult(
        fingerprint=fingerprint,
        title=candidate.title,
        url=candidate.url,
        source_id=source.id,
        source_name=source.name,
        source_type=source.source_type,
        reliability=source.reliability,
        published_at=published_at,
        matched_keywords=matched_keywords,
        score=score,
        first_seen_at=collected_at,
    )


def collect_jobs(
    config: WatchConfig,
    fetch_text: FetchText,
    *,
    now: datetime | None = None,
    known_fingerprints: set[str] | None = None,
) -> tuple[list[JobResult], list[str]]:
    collected_at = now or datetime.now(UTC)
    known = known_fingerprints or set()
    jobs: dict[str, JobResult] = {}
    errors: list[str] = []
    for source in config.sources:
        if not source.enabled:
            continue
        candidates: dict[str, CandidateLink] = {}
        for listing_url in listing_urls_for_source(source):
            try:
                listing_html = fetch_with_retry(
                    fetch_text,
                    listing_url,
                    tuple(source.allowed_hosts),
                    source.request_interval_seconds,
                )
                page_candidates = extract_candidate_links(listing_html, listing_url, source)
                for candidate in page_candidates:
                    if (
                        candidate.published_at is None
                        or candidate.published_at >= config.history_start_date
                    ):
                        candidates.setdefault(candidate.url, candidate)
                if any(
                    candidate.published_at is not None
                    and candidate.published_at < config.history_start_date
                    for candidate in page_candidates
                ):
                    break
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as error:
                errors.append(f"{source.id} listing {listing_url}: {error}")

        detail_pages_fetched = 0
        for candidate in candidates.values():
            try:
                candidate_fingerprint = hashlib.sha256(candidate.url.encode()).hexdigest()
                if candidate_fingerprint in known:
                    continue
                title_match = match_job(
                    candidate.title,
                    "",
                    config,
                    campus_scope=source.campus_scope,
                )

                # Dated title matches can be accepted without another request. This keeps
                # large university job boards cheap while preserving detail-page capacity
                # for company-level campus recruitment announcements.
                if title_match is not None and (
                    candidate.published_at is not None or source.match_from_listing_only
                ):
                    job = build_job_result(
                        candidate,
                        source,
                        title_match,
                        "",
                        collected_at,
                        config,
                    )
                    if job is not None:
                        jobs[job.fingerprint] = job
                    continue

                if source.match_from_listing_only:
                    continue

                should_fetch_detail = title_match is not None or title_has_campus_marker(
                    candidate.title, config
                )
                if not should_fetch_detail or detail_pages_fetched >= source.max_detail_pages:
                    continue
                detail_html = fetch_with_retry(
                    fetch_text,
                    candidate.url,
                    tuple(source.allowed_hosts),
                    source.request_interval_seconds,
                )
                detail_pages_fetched += 1
                detail_text = extract_page_text(detail_html, source.detail_content_selector)
                detail_match = match_job(
                    candidate.title,
                    detail_text,
                    config,
                    campus_scope=source.campus_scope,
                )
                if detail_match is None:
                    continue
                job = build_job_result(
                    candidate,
                    source,
                    detail_match,
                    detail_text,
                    collected_at,
                    config,
                )
                if job is not None:
                    jobs[job.fingerprint] = job
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as error:
                errors.append(f"{source.id} detail {candidate.url}: {error}")
    ordered = sorted(
        jobs.values(),
        key=lambda job: (job.score, job.reliability, job.published_at or date.min),
        reverse=True,
    )
    return ordered, errors


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(item) for item in data.get("fingerprints", [])}


def save_seen(path: Path, fingerprints: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "fingerprints": sorted(set(fingerprints)),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_history(path: Path) -> dict[str, JobResult]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    history: dict[str, JobResult] = {}
    for item in payload.get("jobs", []):
        job = JobResult(
            fingerprint=str(item["fingerprint"]),
            title=str(item["title"]),
            url=str(item["url"]),
            source_id=str(item["source_id"]),
            source_name=str(item["source_name"]),
            source_type=str(item["source_type"]),
            reliability=int(item["reliability"]),
            published_at=(
                date.fromisoformat(str(item["published_at"])) if item.get("published_at") else None
            ),
            matched_keywords=tuple(str(value) for value in item["matched_keywords"]),
            score=int(item["score"]),
            first_seen_at=datetime.fromisoformat(str(item["first_seen_at"])),
        )
        history[job.fingerprint] = job
    return history


def save_history(path: Path, jobs: Iterable[JobResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "jobs": [
            {
                "fingerprint": job.fingerprint,
                "title": job.title,
                "url": job.url,
                "source_id": job.source_id,
                "source_name": job.source_name,
                "source_type": job.source_type,
                "reliability": job.reliability,
                "published_at": job.published_at.isoformat() if job.published_at else None,
                "matched_keywords": list(job.matched_keywords),
                "score": job.score,
                "first_seen_at": job.first_seen_at.isoformat(),
            }
            for job in jobs
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_reports(
    report_dir: Path,
    jobs: list[JobResult],
    new_fingerprints: set[str],
    errors: list[str],
    *,
    report_date: date | None = None,
    history_start_date: date | None = None,
) -> tuple[Path, Path]:
    day = report_date or datetime.now(UTC).date()
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / f"{day.isoformat()}.md"
    csv_path = report_dir / f"{day.isoformat()}.csv"
    history_label = history_start_date.isoformat() if history_start_date else "配置起始日期"
    lines = [
        f"# {day.isoformat()} 秋招岗位监控",
        "",
        f"自 {history_label} 累计 {len(jobs)} 条，本次新增 {len(new_fingerprints)} 条。",
        "",
        "| 新增 | 岗位 | 来源 | 发布日期 | 关键词 | 分数 | 可信度 |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for job in jobs:
        marker = "是" if job.fingerprint in new_fingerprints else "否"
        title = job.title.replace("|", "\\|")
        keywords = "、".join(job.matched_keywords).replace("|", "\\|")
        published_at = job.published_at.isoformat() if job.published_at else "未知"
        lines.append(
            f"| {marker} | [{title}]({job.url}) | {job.source_name} | {published_at} | "
            f"{keywords} | {job.score} | {job.reliability}/5 |"
        )
    if errors:
        lines.extend(["", "## 采集错误", ""])
        lines.extend(f"- {error}" for error in errors)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (report_dir / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "is_new",
                "title",
                "url",
                "source",
                "source_type",
                "published_at",
                "keywords",
                "score",
                "reliability",
            ]
        )
        for job in jobs:
            writer.writerow(
                [
                    job.fingerprint in new_fingerprints,
                    job.title,
                    job.url,
                    job.source_name,
                    job.source_type,
                    job.published_at.isoformat() if job.published_at else "",
                    ",".join(job.matched_keywords),
                    job.score,
                    job.reliability,
                ]
            )
    (report_dir / "cumulative.csv").write_bytes(csv_path.read_bytes())
    return markdown_path, csv_path
