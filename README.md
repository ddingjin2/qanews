# QAnews Daily Digest

RSS 피드에서 QA 및 테스팅 관련 최신 게시글과 뉴스 링크를 수집하고, 새로 발견된 글만 Slack Incoming Webhook 또는 Discord Webhook으로 전송하는 Python CLI 스크립트입니다.

매일 오전 11시(KST)에 cron으로 실행하는 운영을 전제로 하며, 이미 보낸 URL은 SQLite DB에 기록해 중복 발송을 방지합니다. 일반 QA/테스팅 글을 함께 포함하며, 기본 조회 범위는 최근 7일입니다.

## 설치 방법

Python 3.10 이상을 사용합니다.

```bash
cd /path/to/qanews
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell에서는 다음처럼 가상환경을 활성화할 수 있습니다.

```powershell
cd C:\path\to\qanews
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## .env 설정 방법

`.env.example`을 참고해 `.env` 파일을 만듭니다.

```env
SLACK_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=
DATABASE_PATH=./data/digest.db
MAX_POSTS=10
SOURCE_MAX_POSTS=3
LOOKBACK_HOURS=168
MIN_SCORE=2
SEND_EMPTY_DIGEST=false
```

- `SLACK_WEBHOOK_URL`: Slack Incoming Webhook URL입니다.
- `DISCORD_WEBHOOK_URL`: Discord Webhook URL입니다.
- `SLACK_WEBHOOK_URL` 또는 `DISCORD_WEBHOOK_URL` 중 하나 이상이 설정되어야 실제 전송이 가능합니다.
- `DATABASE_PATH`: SQLite DB 경로입니다. 기본값은 `./data/digest.db`입니다.
- `MAX_POSTS`: 한 번에 보낼 최대 게시글 수입니다.
- `SOURCE_MAX_POSTS`: 한 소스에서 한 번에 보낼 최대 게시글 수입니다. `0` 이하로 설정하면 제한하지 않습니다.
- `LOOKBACK_HOURS`: 최근 몇 시간 이내 게시글을 볼지 정합니다. QA 관련 RSS 글 빈도를 고려해 기본값은 168시간입니다.
- `MIN_SCORE`: 이 점수 이상인 글만 발송 후보가 됩니다.
- `SEND_EMPTY_DIGEST`: 신규 글이 없을 때 Webhook 메시지를 보낼지 정합니다.

## sources.yaml 설정 방법

`sources.yaml`에서 RSS 피드 목록을 관리합니다.

```yaml
rss:
  - name: Software Testing Magazine
    url: https://www.softwaretestingmagazine.com/feed/
  - name: Global App Testing Blog
    url: https://www.globalapptesting.com/blog/rss.xml
  - name: TestLodge Blog
    url: https://blog.testlodge.com/feed/
  - name: QASource Blog
    url: https://www.qasource.com/blog/rss.xml
  - name: Google Testing Blog
    url: https://testing.googleblog.com/atom.xml
  - name: Applitools Blog
    url: https://applitools.com/blog/feed/
  - name: BrowserStack Blog
    url: https://www.browserstack.com/blog/feed/
  - name: Katalon Blog
    url: https://katalon.com/resources-center/blog/rss.xml
  - name: Automation Panda
    url: https://automationpanda.com/feed/
  - name: Satisfice Blog
    url: https://www.satisfice.com/blog/feed
  - name: DevelopSense Blog
    url: https://developsense.com/blog/feed/
  - name: Martin Fowler
    url: https://martinfowler.com/feed.atom
  - name: GitHub Engineering
    url: https://github.blog/engineering/feed/
  - name: Meta Engineering
    url: https://engineering.fb.com/feed/
  - name: LINE Engineering KR
    url: https://engineering.linecorp.com/ko/feed/
  - name: Kakao Tech
    url: https://tech.kakao.com/feed/
  - name: Naver D2
    url: https://d2.naver.com/d2.atom
  - name: Woowahan Tech
    url: https://techblog.woowahan.com/feed/
  - name: Toss Tech
    url: https://toss.tech/rss.xml
  - name: Daangn Tech
    url: https://medium.com/feed/daangn
  - name: Banksalad Tech
    url: https://blog.banksalad.com/rss.xml
  - name: Spoqa Tech
    url: https://spoqa.github.io/rss.xml
  - name: 29CM Tech
    url: https://medium.com/feed/29cm
  - name: Hyperconnect Tech
    url: https://hyperconnect.github.io/feed.xml
  - name: Reddit SoftwareTesting QA Search
    url: "https://www.reddit.com/r/softwaretesting/search.rss?q=QA%20OR%20testing%20OR%20test%20automation&restrict_sr=1&sort=new"
  - name: Reddit QualityAssurance Search
    url: "https://www.reddit.com/r/QualityAssurance/search.rss?q=QA%20OR%20testing%20OR%20automation%20OR%20playtesting&restrict_sr=1&sort=new"
  - name: Reddit GameDev QA Search
    url: "https://www.reddit.com/r/gamedev/search.rss?q=QA%20OR%20testing%20OR%20playtesting&restrict_sr=1&sort=new"
```

LinkedIn, Twitter/X처럼 기본 RSS를 제공하지 않거나 로그인이 필요한 SNS는 기본 수집 대상이 아닙니다.

API를 사용하지 않는 범위에서 RSS/Atom 피드만 수집합니다. 기본 소스에는 해외 QA/테스팅 블로그, 일부 글로벌 엔지니어링 블로그, 한국 IT 기업 테크 블로그, Reddit 공개 RSS 검색이 포함되어 있습니다. Reddit은 환경에 따라 403/429를 반환할 수 있으므로, 해당 소스가 실패해도 다른 RSS 소스 처리는 계속됩니다.

## dry-run 실행 방법

Slack 또는 Discord로 전송하지 않고 터미널에 결과만 출력합니다. DB에도 발송 기록을 남기지 않습니다.

```bash
python main.py --dry-run
```

dry-run은 후보가 0개일 때도 다음 진단 정보를 출력합니다.

- RSS에서 수집한 전체 글 수
- 날짜 필터 통과 수
- DB 중복 제외 후 수
- 점수 필터 통과 수
- 최종 발송 후보 수
- 소스별 HTTP status, entry 수, 파싱 경고

## 실제 실행 방법

`.env`에 `SLACK_WEBHOOK_URL` 또는 `DISCORD_WEBHOOK_URL`을 설정한 뒤 실행합니다.

```bash
python main.py
```

설정된 모든 Webhook 전송이 성공한 뒤에만 `posts.sent_at`이 기록됩니다.

## cron 설정 방법

매일 오전 11시(KST)에 실행하려면 서버 timezone을 KST로 맞춘 뒤 다음 cron을 등록합니다.

```cron
0 11 * * * cd /path/to/qanews && /usr/bin/python3 main.py >> logs/digest.log 2>&1
```

서버 timezone이 KST가 아니라면 cron 실행 시간을 KST 기준으로 변환해서 등록해야 합니다.

## 로그 확인 방법

스크립트는 `logs/digest.log`에 실행 로그와 실패 로그를 남깁니다. 운영 중 원인 추적을 위해 실행 후 로그를 자동 삭제하지 않습니다. 대신 로그 파일은 약 1MB 단위로 최대 5개까지 로테이션됩니다.

```bash
tail -f logs/digest.log
```

네트워크 실패, RSS 파싱 경고, Slack/Discord Webhook 실패, SQLite 실패는 로그에 기록됩니다.

스크립트는 `sys.dont_write_bytecode = True`를 설정해 일반 실행 시 `__pycache__` 생성을 방지합니다.

## 중복 발송 방지 방식

RSS 항목의 URL은 normalize한 뒤 SQLite `posts.url`에 UNIQUE 값으로 저장합니다.

1. RSS에서 후보 글을 수집합니다.
2. normalize된 URL이 DB에 이미 있으면 제외합니다.
3. 설정된 모든 Webhook 전송이 성공한 글만 `posts` 테이블에 저장하고 `sent_at`을 기록합니다.
4. 다음 실행에서 같은 URL이 다시 발견되면 DB에 이미 있으므로 발송 후보에서 제외됩니다.

예시:

- 첫 번째 실행: 신규 URL 5개 발견, 설정된 Webhook으로 5개 전송, DB에 `sent_at` 기록
- 두 번째 실행: 같은 URL 5개 다시 발견, DB에 이미 존재하므로 제외, 중복 전송하지 않음

## 키워드 점수 예시

### 예시 1

입력 RSS 항목:

```text
title: "How to improve game QA with better bug reports"
summary: "A practical guide for QA testers working on game testing workflows."
url: "https://example.com/game-qa-bug-report"
```

예상 결과:

- positive keyword가 title과 summary와 url에서 발견됨
- score >= MIN_SCORE
- Webhook 발송 후보에 포함

### 예시 2

입력 RSS 항목:

```text
title: "New RPG walkthrough and cheat guide"
summary: "Complete guide and download links."
url: "https://example.com/rpg-walkthrough"
```

예상 결과:

- negative keyword가 발견됨
- score가 낮음
- Webhook 발송 후보에서 제외

## 제외 범위

이 프로젝트는 MVP 범위의 RSS 기반 자동화 스크립트입니다.

- LinkedIn, Twitter/X, 로그인 필요한 SNS 크롤링은 구현하지 않습니다.
- GitHub Actions는 사용하지 않습니다.
- Telegram은 사용하지 않습니다.
- LLM/API 분석은 사용하지 않습니다.
