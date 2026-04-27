from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
import yaml
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "digest.db"
DEFAULT_SOURCES_PATH = BASE_DIR / "sources.yaml"
LOG_PATH = BASE_DIR / "logs" / "digest.log"
KST = timezone(timedelta(hours=9))
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5
RSS_REQUEST_TIMEOUT = 20
RSS_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QAnews/0.1; +https://github.com/ddingjin2/qanews)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

sys.dont_write_bytecode = True

POSITIVE_KEYWORDS = [
    "game qa",
    "game testing",
    "video game testing",
    "playtest",
    "playtesting",
    "qa tester",
    "bug report",
    "test case",
    "test automation",
    "unity testing",
    "unreal testing",
    "localization qa",
    "compliance testing",
    "console certification",
    "TRC",
    "TCR",
    "XR",
    "qa automation",
    "automated testing",
    "automated test",
    "regression testing",
    "smoke test",
    "build verification",
    "test framework",
    "unity test framework",
    "unreal automation",
    "unreal automated testing",
    "functional testing",
    "compatibility testing",
    "localization testing",
    "accessibility testing",
    "player feedback",
    "user research",
    "beta test",
    "closed beta",
    "open beta",
    "gameplay bug",
    "game bug",
    "crash report",
    "bug triage",
    "certification",
    "console compliance",
    "submission",
    "software testing",
    "quality assurance",
    "quality engineering",
    "qa testing",
    "qa process",
    "qa strategy",
    "test strategy",
    "test management",
    "manual testing",
    "exploratory testing",
    "automation testing",
    "quality control",
    "defect management",
    "defect tracking",
    "release testing",
    "risk based testing",
    "human-in-the-loop",
    "품질",
    "품질관리",
    "품질 관리",
    "품질 보증",
    "테스트",
    "테스팅",
    "자동화 테스트",
    "테스트 자동화",
    "회귀 테스트",
    "스모크 테스트",
    "검증",
    "릴리즈",
    "배포",
    "장애",
    "장애 대응",
    "장애 예방",
    "모니터링",
    "버그",
    "결함",
    "결함 관리",
    "안정성",
    "신뢰성",
    "운영 안정성",
    "성능 테스트",
    "부하 테스트",
    "테스트 케이스",
    "QA",
]

NEGATIVE_KEYWORDS = [
    "walkthrough",
    "cheat",
    "mod menu",
    "sale",
    "giveaway",
    "game review",
    "download",
]

BROAD_GAME_KEYWORDS = [
    "game development",
    "gamedev",
]

QA_CONTEXT_KEYWORDS = [
    "qa",
    "quality",
    "test",
    "testing",
    "playtest",
    "playtesting",
    "bug",
    "crash",
    "certification",
    "compliance",
    "localization",
    "accessibility",
]

GENERAL_QA_KEYWORDS = [
    "qa",
    "quality assurance",
    "quality engineering",
    "software testing",
    "testing",
    "test automation",
    "manual testing",
    "automation testing",
    "exploratory testing",
    "test management",
    "품질",
    "품질 보증",
    "테스트",
    "테스팅",
    "테스트 자동화",
    "검증",
    "장애",
    "배포",
    "릴리즈",
    "버그",
    "결함",
    "안정성",
    "신뢰성",
]

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
}


@dataclass(frozen=True)
class Source:
    name: str
    url: str


@dataclass(frozen=True)
class CandidatePost:
    title: str
    url: str
    source: str
    published_at: str | None
    first_seen_at: str
    score: int
    summary: str


@dataclass
class SourceStats:
    name: str
    url: str
    status: int | str | None = None
    fetched_count: int = 0
    parse_warning: str | None = None
    error: str | None = None


@dataclass
class CollectionStats:
    total_fetched: int = 0
    date_passed: int = 0
    db_passed: int = 0
    score_passed: int = 0
    final_candidates: int = 0
    source_stats: list[SourceStats] | None = None


def ensure_directories() -> None:
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.handlers.RotatingFileHandler(
                LOG_PATH,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )


def str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logging.warning("Invalid integer for %s=%r. Using default %s.", name, raw_value, default)
        return default


def database_path_from_env() -> Path:
    raw_path = os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
    path = Path(raw_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def load_sources(path: Path = DEFAULT_SOURCES_PATH) -> list[Source]:
    if not path.exists():
        raise FileNotFoundError(f"sources.yaml not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    rss_items = config.get("rss", [])
    if not isinstance(rss_items, list):
        raise ValueError("sources.yaml must contain an 'rss' list.")

    sources: list[Source] = []
    for item in rss_items:
        if not isinstance(item, dict):
            logging.warning("Skipping invalid RSS source entry: %r", item)
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if not name or not url:
            logging.warning("Skipping RSS source with missing name or url: %r", item)
            continue
        sources.append(Source(name=name, url=url))

    return sources


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            source TEXT,
            published_at TEXT,
            first_seen_at TEXT NOT NULL,
            sent_at TEXT,
            score INTEGER NOT NULL,
            summary TEXT
        )
        """
    )
    conn.commit()
    return conn


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or parsed.path

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower in TRACKING_QUERY_KEYS or key_lower.startswith(TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))

    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def entry_datetime(entry: Any) -> datetime:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed_time = getattr(entry, attr, None)
        if parsed_time:
            return datetime(*parsed_time[:6], tzinfo=timezone.utc)

    for attr in ("published", "updated", "created"):
        raw_date = getattr(entry, attr, None)
        if raw_date:
            try:
                dt = parsedate_to_datetime(raw_date)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (TypeError, ValueError):
                logging.debug("Could not parse date %r", raw_date)

    return datetime.now(timezone.utc)


def isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def keyword_score(title: str, summary: str, url: str) -> int:
    lowered_title = title.lower()
    lowered_summary = summary.lower()
    lowered_url = url.lower()
    score = 0

    for keyword in POSITIVE_KEYWORDS:
        lowered_keyword = keyword.lower()
        if lowered_keyword in lowered_title:
            score += 3
        if lowered_keyword in lowered_summary:
            score += 2
        if lowered_keyword in lowered_url:
            score += 1

    for keyword in NEGATIVE_KEYWORDS:
        lowered_keyword = keyword.lower()
        if (
            lowered_keyword in lowered_title
            or lowered_keyword in lowered_summary
            or lowered_keyword in lowered_url
        ):
            score -= 3

    searchable_text = f"{lowered_title} {lowered_summary} {lowered_url}"
    has_broad_game_keyword = any(keyword in searchable_text for keyword in BROAD_GAME_KEYWORDS)
    has_qa_context = any(keyword in searchable_text for keyword in QA_CONTEXT_KEYWORDS)
    if has_broad_game_keyword and has_qa_context:
        score += 1

    title_summary_text = f"{lowered_title} {lowered_summary}"
    has_general_qa_keyword = any(keyword in title_summary_text for keyword in GENERAL_QA_KEYWORDS)
    if score == 0 and has_general_qa_keyword:
        score = 2

    return score


def sent_url_exists(conn: sqlite3.Connection, url: str) -> bool:
    cursor = conn.execute("SELECT 1 FROM posts WHERE url = ? LIMIT 1", (url,))
    return cursor.fetchone() is not None


def parse_feed(source: Source) -> tuple[Any, int | str | None]:
    try:
        response = requests.get(
            source.url,
            headers=RSS_REQUEST_HEADERS,
            timeout=RSS_REQUEST_TIMEOUT,
        )
        status = response.status_code
        response.raise_for_status()
        return feedparser.parse(response.content), status
    except requests.RequestException:
        fallback_feed = feedparser.parse(source.url, request_headers=RSS_REQUEST_HEADERS)
        fallback_status = getattr(fallback_feed, "status", None)
        if fallback_feed.entries and not str(fallback_status).startswith(("4", "5")):
            return fallback_feed, fallback_status
        raise


def fetch_candidates(
    sources: list[Source],
    conn: sqlite3.Connection,
    lookback_hours: int,
    min_score: int,
) -> tuple[list[CandidatePost], CollectionStats]:
    now = datetime.now(timezone.utc)
    first_seen_at = isoformat_utc(now)
    cutoff = now - timedelta(hours=lookback_hours)
    candidates: list[CandidatePost] = []
    stats = CollectionStats(source_stats=[])

    for source in sources:
        source_stats = SourceStats(name=source.name, url=source.url)
        assert stats.source_stats is not None
        stats.source_stats.append(source_stats)

        try:
            feed, status = parse_feed(source)
        except requests.RequestException as exc:
            logging.exception("Failed to fetch RSS feed: %s (%s)", source.name, source.url)
            if getattr(exc, "response", None) is not None:
                source_stats.status = exc.response.status_code
            source_stats.error = "fetch failed"
            continue
        except Exception:
            logging.exception("Failed to parse RSS feed: %s (%s)", source.name, source.url)
            source_stats.error = "parse failed"
            continue

        source_stats.status = status
        source_stats.fetched_count = len(feed.entries)
        stats.total_fetched += len(feed.entries)

        if feed.bozo:
            warning = str(feed.bozo_exception)
            source_stats.parse_warning = warning
            logging.warning("RSS parse warning for %s: %s", source.name, warning)

        for entry in feed.entries:
            title = strip_html(str(getattr(entry, "title", "")).strip())
            raw_url = str(getattr(entry, "link", "")).strip()
            if not title or not raw_url:
                continue

            published_dt = entry_datetime(entry)
            if published_dt < cutoff:
                continue
            stats.date_passed += 1

            url = normalize_url(raw_url)
            if sent_url_exists(conn, url):
                continue
            stats.db_passed += 1

            summary = strip_html(
                str(getattr(entry, "summary", "") or getattr(entry, "description", "") or "")
            )
            score = keyword_score(title=title, summary=summary, url=url)
            if score < min_score:
                continue
            stats.score_passed += 1

            candidates.append(
                CandidatePost(
                    title=title,
                    url=url,
                    source=source.name,
                    published_at=isoformat_utc(published_dt),
                    first_seen_at=first_seen_at,
                    score=score,
                    summary=summary,
                )
            )

    unique_by_url: dict[str, CandidatePost] = {}
    for candidate in candidates:
        current = unique_by_url.get(candidate.url)
        if current is None or candidate.score > current.score:
            unique_by_url[candidate.url] = candidate

    sorted_candidates = sorted(unique_by_url.values(), key=lambda post: post.score, reverse=True)
    stats.final_candidates = len(sorted_candidates)
    return sorted_candidates, stats


def format_digest(posts: list[CandidatePost], digest_date: datetime) -> str:
    lines = [f"[QAnews Daily Digest] {digest_date.astimezone(KST).date().isoformat()}"]
    for index, post in enumerate(posts, start=1):
        lines.extend(
            [
                "",
                f"{index}. {post.title}",
                f"출처: {post.source}",
                f"점수: {post.score}",
                f"링크: {post.url}",
            ]
        )
    return "\n".join(lines)


def limit_posts_per_source(posts: list[CandidatePost], source_max_posts: int) -> list[CandidatePost]:
    if source_max_posts <= 0:
        return posts

    selected: list[CandidatePost] = []
    source_counts: dict[str, int] = {}
    for post in posts:
        current_count = source_counts.get(post.source, 0)
        if current_count >= source_max_posts:
            continue
        selected.append(post)
        source_counts[post.source] = current_count + 1

    return selected


def send_to_slack(webhook_url: str, message: str) -> None:
    response = requests.post(webhook_url, json={"text": message}, timeout=15)
    response.raise_for_status()


def send_to_discord(webhook_url: str, message: str) -> None:
    response = requests.post(webhook_url, json={"content": message}, timeout=15)
    response.raise_for_status()


def send_to_configured_webhooks(message: str, slack_webhook_url: str, discord_webhook_url: str) -> None:
    if slack_webhook_url:
        send_to_slack(slack_webhook_url, message)
        logging.info("Sent digest to Slack.")

    if discord_webhook_url:
        send_to_discord(discord_webhook_url, message)
        logging.info("Sent digest to Discord.")


def record_sent_posts(conn: sqlite3.Connection, posts: list[CandidatePost]) -> None:
    sent_at = isoformat_utc(datetime.now(timezone.utc))
    with conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO posts
                (title, url, source, published_at, first_seen_at, sent_at, score, summary)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    post.title,
                    post.url,
                    post.source,
                    post.published_at,
                    post.first_seen_at,
                    sent_at,
                    post.score,
                    post.summary,
                )
                for post in posts
            ],
        )


def format_collection_stats(stats: CollectionStats, final_selected_count: int) -> str:
    lines = [
        "",
        "[Dry-run Diagnostics]",
        f"- RSS에서 수집한 전체 글 수: {stats.total_fetched}",
        f"- 날짜 필터 통과 수: {stats.date_passed}",
        f"- DB 중복 제외 후 수: {stats.db_passed}",
        f"- 점수 필터 통과 수: {stats.score_passed}",
        f"- 최종 발송 후보 수: {final_selected_count}",
    ]

    if stats.source_stats:
        lines.append("- 소스별 상태:")
        for source in stats.source_stats:
            status = source.status if source.status is not None else "unknown"
            detail = f"  - {source.name}: status={status}, entries={source.fetched_count}"
            if source.parse_warning:
                detail += f", warning={source.parse_warning}"
            if source.error:
                detail += f", error={source.error}"
            lines.append(detail)

    return "\n".join(lines)


def print_dry_run(
    posts: list[CandidatePost],
    send_empty_digest: bool,
    stats: CollectionStats,
) -> None:
    if posts:
        print(format_digest(posts, datetime.now(timezone.utc)))
        print(format_collection_stats(stats, len(posts)))
        return

    if send_empty_digest:
        print("신규 QA 관련 글이 없습니다.")
    else:
        print("신규 QA 관련 글이 없습니다. SEND_EMPTY_DIGEST=false 이므로 전송하지 않습니다.")
    print(format_collection_stats(stats, len(posts)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect QA RSS links and send a Slack or Discord digest."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest without sending to Slack or Discord.",
    )
    return parser.parse_args()


def main() -> int:
    configure_console_encoding()
    ensure_directories()
    setup_logging()
    load_dotenv(BASE_DIR / ".env")
    args = parse_args()

    db_path = database_path_from_env()
    max_posts = int_from_env("MAX_POSTS", 10)
    source_max_posts = int_from_env("SOURCE_MAX_POSTS", 3)
    lookback_hours = int_from_env("LOOKBACK_HOURS", 168)
    min_score = int_from_env("MIN_SCORE", 2)
    send_empty_digest = str_to_bool(os.getenv("SEND_EMPTY_DIGEST"), default=False)

    try:
        sources = load_sources()
    except (FileNotFoundError, ValueError):
        logging.exception("Could not load RSS sources.")
        return 1

    if not sources:
        logging.error("No RSS sources configured.")
        return 1

    try:
        with init_db(db_path) as conn:
            all_candidates, stats = fetch_candidates(
                sources=sources,
                conn=conn,
                lookback_hours=lookback_hours,
                min_score=min_score,
            )
            posts = limit_posts_per_source(all_candidates, source_max_posts)[:max_posts]

            logging.info("Selected %s post(s) for digest.", len(posts))

            if args.dry_run:
                print_dry_run(posts, send_empty_digest, stats)
                return 0

            slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
            discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
            if not slack_webhook_url and not discord_webhook_url:
                logging.error(
                    "At least one of SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL is required "
                    "unless --dry-run is used."
                )
                return 1

            if not posts:
                if not send_empty_digest:
                    logging.info("No new posts. SEND_EMPTY_DIGEST=false, nothing sent.")
                    return 0
                send_to_configured_webhooks(
                    "신규 QA 관련 글이 없습니다.",
                    slack_webhook_url=slack_webhook_url,
                    discord_webhook_url=discord_webhook_url,
                )
                logging.info("Sent empty digest message.")
                return 0

            message = format_digest(posts, datetime.now(timezone.utc))
            send_to_configured_webhooks(
                message,
                slack_webhook_url=slack_webhook_url,
                discord_webhook_url=discord_webhook_url,
            )
            record_sent_posts(conn, posts)
            logging.info("Recorded %s URL(s).", len(posts))
            return 0
    except requests.RequestException:
        logging.exception("Webhook request failed.")
        return 1
    except sqlite3.Error:
        logging.exception("SQLite operation failed.")
        return 1
    except Exception:
        logging.exception("Unexpected failure.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
