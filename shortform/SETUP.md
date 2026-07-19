# 준비물 체크리스트 — 계정·API 키 발급 상세 가이드

단계(Phase)별로 나눴다. **1단계만 채우면 첫 영상이 나온다.** 나머지는
운영을 확장하면서 순서대로 채우면 된다. 발급한 값은 전부
`shortform/.env`에 넣는다 (git에 올라가지 않음).

---

## 1단계 — 첫 영상 렌더 (오늘 할 것)

### ☐ Python 3.11 이상
- https://www.python.org/downloads/ → 설치 시 **"Add python.exe to PATH" 반드시 체크**
- 확인: PowerShell에서 `python --version`

### ☐ ffmpeg
- PowerShell: `winget install ffmpeg` → **새 터미널 열고** `ffmpeg -version` 확인
- 안 되면 https://www.gyan.dev/ffmpeg/builds/ 에서 full 빌드 받아 압축 해제 후
  `bin` 폴더를 시스템 PATH에 추가

### ☐ Pretendard 폰트 (자막용)
- https://github.com/orioncactus/pretendard/releases → 최신 버전 다운로드
- `Pretendard-Bold.otf` 우클릭 → "모든 사용자용으로 설치"

### ☐ Anthropic API 키 (대본·심사용 — 필수)
1. https://console.anthropic.com 가입 → 좌측 **API Keys** → **Create Key**
2. `sk-ant-...` 키 복사 → `.env`의 `ANTHROPIC_API_KEY=`에 붙여넣기
3. **Billing**에서 결제 수단 등록 + 월 지출 한도 설정 (권장 $50 —
   시스템 자체 예산 가드 `MONTHLY_LLM_BUDGET_USD`와 이중 안전장치)

→ 여기까지 하면: `start.bat` → GUI에서 영상 업로드 → 렌더까지 동작.

---

## 2단계 — 자동 소싱 (해외 트렌드 스캔)

### ☐ Google Cloud 프로젝트 + YouTube Data API 키
1. https://console.cloud.google.com → 상단 프로젝트 선택 → **새 프로젝트**
   (이름: shortform 등)
2. 좌측 메뉴 **API 및 서비스 → 라이브러리** → "YouTube Data API v3" 검색 →
   **사용 설정**
3. 같은 화면에서 "YouTube Analytics API"도 검색 → **사용 설정** (3단계에서 씀)
4. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → API 키**
5. 생성된 키(`AIza...`) → `.env`의 `YOUTUBE_API_KEY=`
- 무료 쿼터 일 10,000 유닛 — 트렌드 스캔·댓글 수집엔 충분

→ 여기까지 하면: GUI "해외 트렌드에서 자동으로 찾기" + 자동 모드의 소싱 동작.

---

## 3단계 — 업로드·Analytics (실제 발행)

### ☐ 유튜브 채널 2개 (계정 분리)
- **해설 채널**: 구글 계정 A로 youtube.com → 채널 만들기
- **상품 채널**: 구글 계정 B(또는 같은 계정의 **브랜드 계정**)로 채널 만들기
- 팁: 한 구글 계정에 브랜드 계정 여러 개를 만들 수 있어 관리가 편하다
  (유튜브 → 설정 → 채널 추가 또는 관리)

### ☐ OAuth 클라이언트 (client_secret.json)
1. GCP 콘솔(2단계 프로젝트) → **API 및 서비스 → OAuth 동의 화면**
   - User Type: **외부** → 앱 이름/이메일 입력 → 저장
   - **⚠️ 중요**: 만들고 나서 **"앱 게시"(프로덕션으로 전환)** 버튼을 눌러라.
     "테스트" 상태로 두면 인증 토큰이 **7일마다 만료**되어 매주 재로그인해야
     한다. 게시 시 "확인되지 않은 앱" 경고가 떠도 본인만 쓰는 앱이라 문제없다
     (인증 화면에서 "고급 → 이동"으로 진행).
2. **사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   - 애플리케이션 유형: **데스크톱 앱**
3. 생성 후 **JSON 다운로드** → 파일명을 `client_secret.json`으로 바꿔
   `shortform/` 폴더(.env 옆)에 저장

### ☐ 첫 인증 (채널별 1회)
- 해설 트랙: 첫 업로드 시 브라우저가 열리면 **해설 채널 계정**으로 로그인
  → `token.youtube.json` 자동 생성
- 상품 트랙: product 트랙 첫 업로드 시 **상품 채널 계정**으로 로그인
  → `token.youtube.product.json` 자동 생성
- 권한 요청 3개(업로드·댓글·Analytics 읽기)가 뜨면 모두 허용
  — 댓글 자동 게시와 완주율 실측에 필요

→ 여기까지 하면: 승인한 영상의 자동 업로드 + 자동 댓글 + 실측 기반 학습 동작.

---

## 4단계 — 수익화 (쿠팡)

### ☐ 쿠팡 파트너스
1. https://partners.coupang.com → 가입 (사업자 정보로)
2. 승인 후: **링크 생성 → 상품 링크** → 본인 쿠팡 상품 URL 붙여넣기 →
   단축 링크(`https://link.coupang.com/a/...`) 발급
3. 상품마다 발급해서 `products.yaml`의 `partners_link:`에 입력
- 주의: 파트너스는 **최종 승인 전 실적 요건**(일정 클릭/구매)이 있다.
  초기 링크도 정상 작동하니 일단 발급해서 쓰면 된다.

### ☐ products.yaml 작성
```powershell
copy products.example.yaml products.yaml
notepad products.yaml
```
- 상품마다: 이름, 1688 상품 URL(`supplier_url`), 쿠팡 URL, 파트너스 링크,
  가격, 셀링포인트, 타깃
- 영상 소스는 시스템이 알아서: 페이지 자동 추출 → 실패 시 아웃리치 초안

### ☐ (해설 채널용) affiliates.yaml — 선택
```powershell
copy affiliates.example.yaml affiliates.yaml
```
- 테크 카테고리 등에 넣을 제휴 링크. 고지 문구는 예시 그대로 유지할 것.

---

## 5단계 — 아웃리치 메일 발송 (선택, 초안 모드는 설정 없이 동작)

### ☐ 방법 A: Resend (추천 — 간단)
1. https://resend.com 가입 → **Domains → Add Domain** (보유 도메인 필요)
2. 안내되는 DNS 레코드(SPF/DKIM)를 도메인 관리 페이지에 추가 → 인증 완료
3. **API Keys → Create** → `.env`에:
   `RESEND_API_KEY=re_...` / `OUTREACH_FROM=contact@내도메인.com`
- 도메인이 없으면 방법 B를 쓰면 된다.

### ☐ 방법 B: Gmail
1. 구글 계정 → **2단계 인증** 활성화 (필수 선행)
2. https://myaccount.google.com/apppasswords → 앱 비밀번호 생성 (16자리)
3. `.env`에: `SMTP_HOST=smtp.gmail.com` / `SMTP_USER=본인@gmail.com` /
   `SMTP_PASSWORD=앱비밀번호16자리`

### ☐ 공통
- `.env`에 `SELLER_NAME=` / `SELLER_STORE=` 입력 (메일 서명에 들어감)
- 자동 발송 원하면 `OUTREACH_AUTO_SEND=true` (기본은 초안 생성 후 검토)
- 1688 공급사는 왕왕 채팅이라 `out/outreach/*.1688.txt` 초안을 복사해
  붙여넣는 방식 (왕왕은 API가 없어 이게 한계)

---

## 6단계 — 알림 (선택, 강력 추천)

### ☐ 텔레그램 봇 (무료, 5분)
1. 텔레그램에서 **@BotFather** 검색 → `/newbot` → 봇 이름·아이디 입력 →
   **토큰**(`123456:AA...`) 발급
2. **@userinfobot** 검색 → `/start` → 내 **챗 ID**(숫자) 확인
3. 만든 봇을 검색해서 **먼저 `/start`를 한 번 보내야** 봇이 나에게 메시지를
   보낼 수 있다 (텔레그램 정책)
4. `.env`에: `TELEGRAM_BOT_TOKEN=` / `TELEGRAM_CHAT_ID=`
- ⚠️ 토큰은 비밀값 — 채팅·문서에 붙여넣었다면 @BotFather `/revoke`로
  재발급할 것
- 받는 알림: 실패/차단, 서킷브레이커(저작권 사고), 주간 톤 회고,
  상품 기회 리포트, 아웃리치 초안 생성/팔로업

### ☐ (대안) Slack/Discord 웹훅
- 웹훅 URL을 `.env`의 `ALERT_WEBHOOK_URL=`에 넣으면 동일하게 동작
  (텔레그램과 동시 사용도 가능)

---

## 7단계 — 나중에 (지금 안 해도 됨)

- ☐ **Instagram Reels**: 프로페셔널(비즈니스) 계정 전환 + 페이스북 페이지
  연결 + Meta 개발자 앱 검수(`instagram_content_publish`) — 검수에 수 주
  걸리므로 유튜브 성과가 나온 뒤 진행 권장
- ☐ **YouTube Shopping 제품 태그**: YPP 가입 + 쇼핑 자격 충족 후 유튜브
  스튜디오에서 수동 연동 (API 없음)
- ☐ **ElevenLabs TTS**: 훅 문장만 고품질 보이스로 교체하고 싶을 때

---

## 최종 확인 — .env 채움 상태

| 변수 | 단계 | 필수 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 1 | ✅ |
| `YOUTUBE_API_KEY` | 2 | 자동 소싱 시 |
| `client_secret.json` (파일) | 3 | 업로드 시 |
| `partners_link` (products.yaml) | 4 | 상품 트랙 시 |
| `RESEND_API_KEY` 또는 `SMTP_*` | 5 | 자동 발송 시 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 6 | 권장 |
| `SELLER_NAME` / `SELLER_STORE` | 5 | 아웃리치 시 |

전부 채웠으면: `start.bat` → 자동 모드 ON → 하루 1~2회 승인 큐 확인.
