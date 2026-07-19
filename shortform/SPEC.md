# 숏폼 자동 생성·등록 파이프라인 스펙 (Codex 작업 지시서)

트렌드 주제 수집 → 원본 롱폼 확보 → 하이라이트 탐지 → 숏폼 편집(컷/템포/줌인/
화면전환/자막/TTS/에셋 애니메이션) → 렌더링 → YouTube Shorts·Instagram Reels
자동 업로드까지 이어지는 24시간 무인 파이프라인.

---

## 0. 하드 제약 — 반드시 먼저 읽고 그대로 구현할 것

이 섹션은 기능 요구사항보다 우선한다. 위반하면 채널이 삭제되고 수익화가
불가능해지므로, "나중에 붙이는 옵션"이 아니라 파이프라인의 게이트로 구현한다.

### 0-1. 소스 권리 게이트 (rights gate)
- 소스 영상은 아래 화이트리스트 중 하나의 `license_type`이 DB에 기록된
  경우에만 편집 단계(M3 이후)로 진입할 수 있다. 미기록 소스는 상태를
  `BLOCKED_RIGHTS`로 전이시키고 파이프라인에서 제외한다.
  - `own` — 본인/자사 채널 원본
  - `licensed` — 서면 계약·허락을 받은 콘텐츠 (계약 문서 경로 필수 기록)
  - `cc_by` — Creative Commons 표시 라이선스 (출처 표기 자동 삽입 필수)
  - `public` — 퍼블릭 도메인, 공공누리 1유형 등 공공저작물
    (정치·시사 카테고리는 국회방송, 정부 브리핑 등 공공저작물 위주로 구성 가능)
- 아이돌 무대·예능·영화 클립은 소속사/방송사/배급사와의 계약(`licensed`)이
  없는 한 자동 소싱 대상에서 제외한다. 방송사 공식 채널 영상을 yt-dlp로
  내려받는 것 자체가 무단 사용이다. Content ID가 업로드 즉시 잡아내며,
  경고 3회면 채널이 통째로 사라진다.
- YouTube 파트너 프로그램은 "재사용 콘텐츠(reused content)" 채널의 수익화를
  거부한다. 타인 영상을 자르기만 한 채널은 조회수가 나와도 수익이 0이다.
  수익화가 목표라면 권리 확보가 선행 조건이지 우회 대상이 아니다.

### 0-2. 발행 승인 게이트 (publish gate)
- 완전 무인 발행은 정책·품질 사고가 채널에 누적된 뒤에야 발견된다.
  기본값은 **승인 큐 모드**: 렌더링 완료본을 큐에 쌓고, 운영자가 웹 대시보드
  (M8)에서 승인한 건만 업로드한다.
- `AUTO_PUBLISH=true` 환경변수로 전환 가능하되, 이 경우에도
  정치·시사 카테고리는 항상 승인 큐를 거친다 (오정보·명예훼손 리스크).
- 하루 업로드 상한을 설정으로 강제한다 (기본 YouTube 3개 / Instagram 3개).

---

## 1. 결과물

- Python 3.12 모노리포. 저장소 루트에 `shortform/app/`로 구현.
- CLI 진입점 하나(`python -m app`)로 전체 파이프라인·개별 스테이지 실행 가능.
- systemd 또는 Docker Compose로 24시간 상주 가능한 스케줄러 포함.
- 승인/모니터링용 로컬 웹 대시보드 (FastAPI + 단일 HTML, 외부 CDN 금지).

## 2. 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| 언어/런타임 | Python 3.12, uv | |
| 다운로드 | yt-dlp | 권리 게이트 통과 소스에만 사용 |
| 전사(STT) | faster-whisper (large-v3, GPU 없으면 medium) | 단어 단위 타임스탬프 필수 |
| 하이라이트 스코어링 | Claude API (`claude-sonnet-5`) | 전사문+오디오/장면 피처를 입력 |
| 장면 감지 | PySceneDetect | 컷 후보 추출 |
| 오디오 분석 | librosa | RMS 에너지, 웃음/함성 피크 |
| 얼굴/피사체 추적 | mediapipe | 9:16 리프레임 크롭 중심점 |
| 편집·렌더 | ffmpeg (filtergraph 직접 생성) | MoviePy 금지 — 느리고 메모리 누수 |
| 자막 | ASS(libass) 자막 → ffmpeg burn-in | 워드 단위 하이라이트 |
| TTS | Edge-TTS (기본) / ElevenLabs (옵션) | 한국어 보이스, 속도 1.1~1.25배 |
| 이미지 에셋 | ChatGPT 생성 PNG를 `shortform/assets/`에 수동 배치 | `ASSET_PROMPTS.md` 참조 |
| DB/큐 | SQLite + 상태 머신 테이블 | 외부 인프라 의존 금지 |
| 업로드 | YouTube Data API v3, Instagram Graph API | §7 참조 |
| 스케줄러 | APScheduler | cron 표현식 설정 파일 |

## 3. 아키텍처 — 상태 머신 파이프라인

각 작업(job)은 SQLite `jobs` 테이블의 행이며 아래 상태를 순서대로 전이한다.
모든 스테이지는 멱등(idempotent)해야 하고, 실패 시 `retry_count`를 올리며
지수 백오프(2/4/8분, 3회)로 재시도, 초과 시 `FAILED`로 전이하고 알림.

```
DISCOVERED → RIGHTS_OK → ACQUIRED → ANALYZED → EDITED → RENDERED
   → (승인 큐) APPROVED → PUBLISHED_YT → PUBLISHED_IG → DONE
실패 분기: BLOCKED_RIGHTS / FAILED / REJECTED(운영자 반려)
```

디렉터리 구조:

```
shortform/
  SPEC.md               ← 이 문서
  ASSET_PROMPTS.md      ← ChatGPT 이미지 에셋 생성 프롬프트 모음
  app/
    __main__.py         # CLI: run-all | stage <name> | serve-dashboard
    config.py           # pydantic-settings, .env 로드
    db.py               # SQLite 스키마 + 상태 전이 함수
    stages/
      m1_discover.py
      m2_acquire.py
      m3_analyze.py
      m4_edit.py
      m5_render.py
      m6_publish.py
    editing/
      timeline.py       # 편집점 → 타임라인 JSON
      reframe.py        # 9:16 크롭 경로 계산
      subtitles.py      # ASS 생성
      tts.py
      ffmpeg_graph.py   # 타임라인 JSON → filtergraph 문자열
    dashboard/
      server.py         # FastAPI 승인 큐 + 상태 보드
      index.html
    scheduler.py
  assets/               # ChatGPT 생성 PNG (자막 박스, 스티커, 로고 등)
  work/                 # 다운로드·중간 산출물 (gitignore)
  out/                  # 최종 mp4 + 메타데이터 JSON (gitignore)
```

## 4. 모듈별 스펙

### M1 — 주제·소스 발굴 (`m1_discover`)
- 입력 소스 2종:
  1. **소스 카탈로그(기본)**: `sources.yaml`에 운영자가 등록한 권리 확보
     채널/플레이리스트/로컬 파일 목록. 각 항목에 `license_type` 필수.
  2. **트렌드 신호(보조)**: YouTube Data API `videos.list(chart=mostPopular,
     regionCode=KR)` + 카테고리 ID로 지금 뜨는 주제 키워드를 뽑는다.
     이 신호는 *어떤 소스를 먼저 편집할지, 제목·해시태그를 뭘로 잡을지*
     우선순위 산정에만 쓰고, 트렌드 영상 자체를 다운로드 대상으로 삼지 않는다.
- 출력: `jobs` 행 생성 (`DISCOVERED`), 카테고리(`idol|variety|movie|politics|etc`),
  우선순위 점수, 트렌드 키워드 목록.

### M2 — 소스 확보 (`m2_acquire`)
- 권리 게이트 검증 후 `RIGHTS_OK` → yt-dlp(원격) 또는 파일 복사(로컬)로
  `work/{job_id}/source.mp4` 확보. 1080p 이상 우선, 오디오 분리 추출(wav).
- 메타데이터(원제, 채널, 길이, 라이선스 근거)를 job에 기록. `ACQUIRED`.

### M3 — 하이라이트 탐지 (`m3_analyze`)
세 신호를 합산해 편집점 후보를 만든 뒤 LLM으로 최종 선정한다.
1. **전사**: faster-whisper로 단어 단위 타임스탬프 전사.
2. **오디오 피처**: librosa RMS 곡선에서 상위 피크 구간(웃음·함성·강조 발화).
3. **장면 컷**: PySceneDetect 컷 리스트.
- 위 신호 + 전사문을 Claude에 넣고 카테고리별 프롬프트로 15~45초짜리
  하이라이트 구간 1~3개를 JSON으로 받는다. 프롬프트에 카테고리 규칙 포함:
  - `idol`: 후렴/킬링파트/무대 포인트 안무 중심, 곡 클라이맥스 직전에서 시작
  - `variety`: 웃음 피크 직전 셋업 4~6초 포함해 펀치라인으로 끝나기
  - `movie`(예고편·리뷰 등 권리 확보분): 긴장 고조 → 컷 아웃, 스포일러 금지 지시
  - `politics`: 발언 맥락이 잘리지 않도록 문장 경계 스냅, 발언자·날짜 자막 강제
- LLM 출력 스키마: `{start, end, hook_text, title, reason, keywords[]}`.
  문장 경계로 스냅(전사 타임스탬프 기준)한 뒤 저장. `ANALYZED`.

### M4 — 편집 결정 (`m4_edit`)
하이라이트 구간을 "타임라인 JSON"으로 컴파일한다. 렌더와 분리해서
편집 로직을 단위 테스트 가능하게 유지한다.
- **컷 편집·템포**: 무음(-35dB, 0.4초 이상) 자동 제거(jump cut).
  카테고리별 평균 샷 길이 목표: variety 1.5~2.5s, idol 2~3s(비트 그리드에
  스냅), politics 4~6s(과편집 금지).
- **리프레임**: mediapipe 얼굴 박스의 EMA 스무딩 경로로 9:16 크롭.
  얼굴 미검출 구간은 중앙 크롭 + 상하 블러 패딩 폴백.
- **줌인/펀치인**: 강조 단어(LLM이 표시) 시점에 1.0→1.08 스케일 0.3초
  ease-out. 같은 샷 내 2회 이상 금지.
- **화면전환**: 기본은 하드컷. 섹션 경계에만 0.2초 crossfade 또는
  whip-pan(가로 블러) 중 택1. 3종 이상 섞지 말 것.
- **자막**: ASS로 워드 단위 팝인(현재 단어 색상 하이라이트, 폰트
  Pretendard Bold, 외곽선+그림자, 세이프존: 하단 25%·상단 12% 회피 —
  Shorts/Reels UI에 가리는 영역). 욕설 마스킹 테이블 적용.
- **TTS 나레이션**: 훅(첫 1.5초) + 필요 시 브릿지 문장을 Edge-TTS로 생성,
  원본 오디오는 TTS 구간에서 -12dB 더킹(sidechaincompress).
- **에셋 애니메이션**: `assets/` PNG 오버레이(스티커, 자막 박스, 채널 로고,
  구독 유도 배지)를 타임라인 이벤트로 배치. 등장은 0.25초 scale-bounce,
  퇴장은 0.15초 fade. 로고는 우상단 상시, 구독 배지는 마지막 2초.
- **아웃트로**: 마지막 1초 CTA 자막 + 다음 영상 유도 문구.
- 출력: `work/{job_id}/timeline.json`. `EDITED`.

### M5 — 렌더링 (`m5_render`)
- `timeline.json` → 단일 ffmpeg 명령의 filtergraph로 컴파일해 실행.
  (trim/concat, crop 키프레임은 `zoompan`/`crop` 표현식, overlay+fade,
  ASS burn-in, loudnorm I=-14 LUFS)
- 출력 규격: 1080x1920, H.264 high, CRF 18, 30fps(원본이 60이면 60 유지),
  AAC 192k. 길이 ≤ 60초(하드 제한 — Shorts는 3분까지 가능하지만 알고리즘
  안전값으로 60초 상한, 설정으로 변경 가능).
- 썸네일 프레임 1장 + 업로드 메타데이터 JSON(제목, 설명, 해시태그,
  CC-BY면 출처 표기 문단 자동 포함) 생성. `RENDERED`.

### M6 — 업로드 (`m6_publish`)
- **YouTube**: Data API v3 `videos.insert` (resumable). OAuth 리프레시 토큰
  파일 보관. 제목 끝 `#Shorts`. `selfDeclaredMadeForKids=false`.
  쿼터 주의: 업로드 1건 = 1,600유닛, 기본 일 쿼터 10,000 → 실질 6건/일.
- **Instagram Reels**: Graph API — 비즈니스 계정 필수. 영상은 공개 URL이어야
  하므로 `out/`을 임시 서명 URL로 서빙하는 업로드 헬퍼 포함
  (`media` 컨테이너 생성 → 상태 폴링 `FINISHED` → `media_publish`).
- 발행 시각: 카테고리별 슬롯(기본 07:30 / 12:30 / 19:30 KST)에 예약 분배.
- 결과 video ID·permalink를 job에 기록. `PUBLISHED_*` → `DONE`.

### M7 — 스케줄러 (`scheduler.py`)
- APScheduler 상주 프로세스: M1 매 2시간, M2~M5는 큐 워커(동시 렌더 1),
  M6은 발행 슬롯 cron. 프로세스 재시작 시 미완료 job 자동 복구(멱등성 활용).

### M8 — 대시보드·모니터링 (`dashboard/`)
- FastAPI: job 목록/상태, 렌더 결과 미리보기(video 태그), 승인/반려 버튼,
  실패 로그 뷰. 반려 시 사유 입력 → M3 프롬프트 개선에 쓸 수 있게 저장.
- 알림: `FAILED`·`BLOCKED_RIGHTS` 발생 시 웹훅(설정된 경우) POST.
- 성과 피드백: 발행 48시간 후 조회수·평균시청지속시간을 API로 수집해
  `performance` 테이블에 적재 → M1 우선순위 가중치에 반영.

## 5. 구현 순서 (Phase)

1. **Phase 1 — 편집 코어 (수동 입출력)**: 로컬 mp4 입력 → M3~M5 →
   `out/` 확인. 이 단계 완성도가 전체 품질을 결정하므로 가장 오래 투자.
2. **Phase 2 — 업로드**: M6 + 승인 대시보드. 수동 승인으로 실발행 검증.
3. **Phase 3 — 자동화**: M1·M2·M7 연결, 승인 큐 모드로 24시간 상주 운전.
4. **Phase 4 — 피드백 루프**: M8 성과 수집 → 하이라이트 프롬프트/우선순위 튜닝.

## 6. 검수 기준

- 로컬 10분 테스트 영상 1개 입력 시 사람 개입 없이 `out/`에 규격 준수
  mp4 + 메타데이터 JSON 생성.
- 자막 싱크 오차 ±0.2초 이내(샘플 20개 단어 수동 대조).
- 렌더 산출물에 검은 여백·세이프존 침범·오디오 클리핑 없음.
- `license_type` 없는 소스 투입 시 `BLOCKED_RIGHTS`로 차단되는 테스트 포함.
- 파이프라인 중간 kill 후 재시작 시 중복 산출물 없이 이어서 완료(멱등성 테스트).
- 시크릿(.env, 토큰 파일)은 gitignore. 저장소에 절대 커밋 금지.

## 7. 운영 메모

- 인스타 Reels API는 비즈니스 계정 전환 + Facebook 페이지 연결 + 앱 검수
  (`instagram_content_publish` 권한)가 선행돼야 한다. 검수 기간을 감안해
  Phase 2에서 YouTube 먼저 실발행하는 것을 권장.
- 수익화 관점 현실치: 재사용 콘텐츠 판정을 피하려면 편집·나레이션·자막이
  "변형적 기여"로 인정될 수준이어야 하고, 그마저도 소스 권리가 없으면
  무의미하다. 초기에는 공공저작물(politics)과 본인 촬영/제작 소스로
  채널 히스토리를 쌓는 구성이 유일하게 지속 가능한 경로다.
