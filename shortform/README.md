# shortform — 번역·해설 쇼츠 자동 파이프라인

해외 바이럴 → 한국어 해설 쇼츠 → YouTube Shorts 자동 발행. 설계 문서는
`SPEC.md`, 판단 방법론은 `PLAYBOOK.md`(사람용) + `app/prompts/`(시스템용).

## 설치

```bash
cd shortform
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[media,serve,dev]"    # 업로드까지: ".[media,serve,publish,dev]"
cp .env.example .env                   # 키 입력
cp sources.example.yaml sources.yaml   # 권리 확보 소스 등록
# ffmpeg 필수: https://ffmpeg.org (PATH에 있어야 함)
```

## 비용 구조 (토큰 최소화 설계)

| 작업 | 실행 위치 | 비용 |
|---|---|---|
| 전사(Whisper), TTS(Edge-TTS), 렌더(ffmpeg) | **전부 로컬** | 무료 |
| 소재 점수·댓글 마이닝 | Claude Haiku (light) | 저가 |
| 대본·제목·리스크 심사 | Claude Opus (heavy) | job당 3회, 전사문은 캐시 공유 |
| 트렌드/댓글 수집 | YouTube Data API | 무료 쿼터 |

M1은 휴리스틱 사전 필터로 LLM 심사 대상을 트랙당 10건으로 제한한다.

## Phase 1 — 편집 코어 검증 (지금 여기부터)

```bash
python -m app ingest ./my_video.mp4 --title "테스트" --license own
python -m app run-once          # 전사→대본→TTS→타임라인→렌더→정책판정
python -m app status
python -m app serve             # http://localhost:8008 승인 큐에서 결과 확인
```

## Phase 2~3 — 발행·자동화

```bash
python -m app stage m6          # 승인된 job 업로드 (OAuth 첫 실행 시 브라우저)
python -m app run               # 24시간 상주: M1 2시간 주기 + 파이프라인 10분 주기
```

## 발행 게이트 (단계적 자율화)

- Level 0(수동) → 1(섀도) → 2(부분 자동) → 3(전자동). 대시보드에서 승급.
- 승급 조건: 최근 200건 엔진-운영자 일치율 95% 이상 (대시보드 상단에 표시).
- 저작권 경고·클레임 발생 시 서킷브레이커가 자동 강등 (`policy.circuit_breaker`).

## 테스트

```bash
pytest            # 편집 규칙(0-1-1)·상태 머신 — 외부 의존성 없음
```

## 디렉터리

```
app/prompts/   판단 방법론 (git 버전 관리 — 수정 시 PLAYBOOK.md와 함께)
app/stages/    M1~M6 파이프라인 스테이지
app/editing/   타임라인 컴파일·TTS·ASS 자막·ffmpeg 그래프
app/policy.py  M10 승인 정책 엔진 + 서킷브레이커
app/optimize.py M9 카테고리 조건부 밴딧 (톤앤매너 학습)
work/ out/     중간 산출물 / 최종 mp4 (gitignore)
```
