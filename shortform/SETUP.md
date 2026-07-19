# 완전 설치 가이드 — 클릭 하나까지

컴퓨터를 처음 만지는 사람 기준으로 썼다. 순서대로 따라오면 된다.
**발급한 값은 전부 `shortform\.env` 파일에 넣는다** (이 파일은 깃허브에
안 올라가니 안전). `.env`를 여는 법은 아래 0단계에 있다.

> 표기 규칙: `이렇게` = 화면에서 찾을 버튼/메뉴 이름. `.env`의 `KEY=` = 그
> 파일에 넣을 항목. UI는 가끔 바뀌니 버튼 이름이 조금 다르면 비슷한 걸 누르면 된다.

---

## 0단계 — 프로젝트 받고 .env 열기

### 0-1. 프로젝트 폴더 받기 (최초 1회)
PowerShell을 연다 (시작 메뉴에서 `PowerShell` 검색 → 실행). 한 줄씩 입력:
```powershell
cd $HOME\Desktop
git clone -b claude/auto-shortform-generation-gmij7s https://github.com/ert93333-ops/ai-agent-playbook.git shortform-project
```
- `git`이 없다는 오류가 나면: https://git-scm.com/download/win 에서 받아
  설치(전부 기본값 Next) 후 PowerShell을 새로 열고 다시.

### 0-2. 이미 받았으면 최신화
```powershell
cd $HOME\Desktop\shortform-project
git pull origin claude/auto-shortform-generation-gmij7s
```

### 0-3. .env 파일 만들고 열기
```powershell
cd $HOME\Desktop\shortform-project\shortform
copy .env.example .env
notepad .env
```
메모장이 열린다. 여기에 아래 단계에서 발급하는 값들을 채워 넣고, 채울
때마다 **Ctrl+S로 저장**한다. 이 창은 계속 열어둬도 된다.

---

## 1단계 — 필수 프로그램 3개 (이것만 하면 첫 영상 나옴)

### 1-1. Python (파이썬)
1. https://www.python.org/downloads/ 접속
2. 노란 버튼 **`Download Python 3.x.x`** 클릭 → 다운로드된 파일 실행
3. ⚠️ 설치 첫 화면 맨 아래 **`Add python.exe to PATH`** 체크박스를 **반드시 체크**
4. **`Install Now`** 클릭 → 완료
5. 확인: PowerShell 새로 열고 `python --version` → `Python 3.x.x` 나오면 성공

### 1-2. ffmpeg (영상 편집 엔진)
PowerShell에 입력:
```powershell
winget install ffmpeg
```
- 설치 후 **PowerShell을 완전히 닫았다 새로 열고** `ffmpeg -version` 확인
- `winget`이 없다는 오류 시: https://www.gyan.dev/ffmpeg/builds/ →
  `ffmpeg-release-full.7z` 다운로드 → 압축 해제 → 안의 `bin` 폴더 경로를
  복사 → 윈도우 `시스템 환경 변수 편집` → `Path` → `새로 만들기` → 붙여넣기

### 1-3. Pretendard 폰트 (자막용)
1. https://github.com/orioncactus/pretendard/releases 접속
2. 맨 위(최신) 릴리스의 **`Assets`** 펼치기 → `Pretendard-1.x.x.zip` 다운로드
3. 압축 풀고 `public\static\` 안의 폰트 전체 선택 → 우클릭 →
   **`모든 사용자용으로 설치`**

### 1-4. Anthropic API 키 (대본·심사 두뇌 — 필수)
1. https://console.anthropic.com 접속 → 가입/로그인
2. 왼쪽 메뉴 **`API keys`** 클릭
3. **`Create Key`** 버튼 → 이름 아무거나(예: shortform) → **`Add`**
4. 뜨는 키 `sk-ant-...` 를 **`Copy`** (이 창 닫으면 다시 못 봄)
5. 메모장 `.env`에서 `ANTHROPIC_API_KEY=` 뒤에 붙여넣기 → **Ctrl+S**
6. 왼쪽 **`Billing`** → **`Add payment method`** 로 카드 등록 →
   **`Set monthly limit`** 에서 한도 설정 (권장 $50)

**여기까지 하면 첫 영상이 나온다.** 테스트:
```powershell
cd $HOME\Desktop\shortform-project\shortform
.\.venv\Scripts\Activate.ps1   # 최초엔 아래 start.bat이 만들어줌
```
그냥 **`shortform` 폴더에서 `start.bat` 더블클릭**하면 설치·실행이 자동으로
되고 브라우저에 스튜디오가 열린다. 영상 하나 올리고 "한 번 실행"을 눌러본다.

---

## 2단계 — 자동 소싱 (해외 트렌드 자동 검색)

### 2-1. Google Cloud 프로젝트 만들기
1. https://console.cloud.google.com 접속 → 구글 로그인
2. 화면 맨 위 파란 바의 프로젝트 이름(또는 **`프로젝트 선택`**) 클릭 →
   오른쪽 위 **`새 프로젝트`**
3. 이름 `shortform` 입력 → **`만들기`** → 생성되면 그 프로젝트로 전환
   (다시 맨 위 프로젝트 선택에서 shortform 클릭)

### 2-2. API 2개 켜기
1. 왼쪽 메뉴(☰) → **`API 및 서비스`** → **`라이브러리`**
2. 검색창에 `YouTube Data API v3` → 결과 클릭 → **`사용`** 버튼
3. 다시 라이브러리로 → `YouTube Analytics API` 검색 → **`사용`** (3단계에서 씀)

### 2-3. API 키 발급
1. 왼쪽 **`API 및 서비스`** → **`사용자 인증 정보`**
2. 위쪽 **`+ 사용자 인증 정보 만들기`** → **`API 키`**
3. 뜨는 키 `AIza...` 복사 → `.env`의 `YOUTUBE_API_KEY=` 뒤에 붙여넣기 → 저장

→ 이제 스튜디오의 **`해외 트렌드에서 자동으로 찾기`** 버튼이 작동한다.

---

## 3단계 — 업로드 + 완주율 실측 (실제 발행)

### 3-1. 유튜브 채널 만들기 (해설용·상품용 2개)
1. https://www.youtube.com 로그인 → 오른쪽 위 프로필 → **`채널 만들기`**
2. 상품 채널은 분리 권장: 프로필 → **`설정`** → **`채널 추가 또는 관리`** →
   **`채널 만들기`** 로 두 번째(브랜드) 채널 생성

### 3-2. OAuth 동의 화면 설정
1. GCP 콘솔(2단계 프로젝트) → **`API 및 서비스`** → **`OAuth 동의 화면`**
2. User Type **`외부`** 선택 → **`만들기`**
3. 앱 이름(shortform), 사용자 지원 이메일, 개발자 이메일 입력 → 나머지
   **`저장 후 계속`** 반복 → 완료
4. ⚠️ **가장 중요**: OAuth 동의 화면 요약에서 **`앱 게시`** (또는
   `프로덕션으로 푸시`) 버튼을 누른다. **테스트 상태로 두면 유튜브 토큰이
   7일마다 만료**되어 매주 재로그인해야 한다. "확인되지 않은 앱" 경고는
   본인만 쓰니 무시하고 진행하면 된다.

### 3-3. OAuth 클라이언트(client_secret.json) 발급
1. **`API 및 서비스`** → **`사용자 인증 정보`** → **`+ 사용자 인증 정보 만들기`**
   → **`OAuth 클라이언트 ID`**
2. 애플리케이션 유형 **`데스크톱 앱`** → 이름 입력 → **`만들기`**
3. 뜨는 창에서 **`JSON 다운로드`** 클릭
4. 다운로드된 파일 이름을 **`client_secret.json`** 으로 바꿔서
   **`shortform` 폴더**(.env 옆)에 넣는다
   - 이름 바꾸기: 파일 우클릭 → 이름 바꾸기. (확장자가 안 보이면 탐색기
     `보기` → `파일 확장명` 체크)

### 3-4. 첫 로그인 (채널당 1회, 자동으로 진행됨)
- 나중에 처음 업로드가 실행될 때 브라우저가 자동으로 열린다. 해설 트랙이면
  **해설 채널 계정**으로, 상품 트랙이면 **상품 채널 계정**으로 로그인하고
  권한 3개(업로드·댓글·Analytics)를 **모두 허용**하면 된다. 토큰 파일
  (`token.youtube.json` 등)이 자동 생성된다.

---

## 4단계 — 쿠팡 수익화

### 4-1. 쿠팡 파트너스
1. https://partners.coupang.com 접속 → **`가입하기`** (사업자 정보로 가입)
2. 승인 후 로그인 → 상단 **`링크 생성`** → **`상품 링크`**
3. 본인 쿠팡 상품 URL 붙여넣기 → 생성된 **`단축 URL`**(`https://link.coupang.com/a/...`) 복사

### 4-2. products.yaml 작성
PowerShell:
```powershell
cd $HOME\Desktop\shortform-project\shortform
copy products.example.yaml products.yaml
notepad products.yaml
```
상품마다 채운다: 이름 / 1688 상품 URL(`supplier_url`) / 쿠팡 URL /
파트너스 링크(`partners_link`) / 가격 / 셀링포인트 / 타깃.
영상 소스는 시스템이 자동 처리(페이지 추출 → 실패 시 아웃리치).

### 4-3. (해설 채널) affiliates.yaml — 선택
```powershell
copy affiliates.example.yaml affiliates.yaml
```
테크 카테고리 등에 넣을 제휴 링크. **고지 문구는 예시 그대로 유지**(공정위 의무).

---

## 5단계 — 아웃리치 메일 자동 발송 (선택)

설정 안 해도 초안 파일(`out\outreach\`)은 자동 생성된다. 자동 발송을
원하면 A 또는 B 중 하나.

### 5-A. Resend (도메인 있으면 추천)
1. https://resend.com 가입
2. 왼쪽 **`Domains`** → **`Add Domain`** → 보유 도메인 입력 → 안내되는
   DNS 레코드(SPF/DKIM)를 도메인 구매처 관리페이지에 추가 → 인증 완료 대기
3. 왼쪽 **`API Keys`** → **`Create API Key`** → 키 복사
4. `.env`: `RESEND_API_KEY=re_...` / `OUTREACH_FROM=contact@내도메인.com`

### 5-B. Gmail (도메인 없을 때)
1. https://myaccount.google.com/security → **`2단계 인증`** 켜기(필수 선행)
2. https://myaccount.google.com/apppasswords → 앱 이름 입력 → **`만들기`** →
   나오는 **16자리 비밀번호** 복사
3. `.env`: `SMTP_HOST=smtp.gmail.com` / `SMTP_USER=본인@gmail.com` /
   `SMTP_PASSWORD=16자리앱비밀번호`

### 5-공통
- `.env`: `SELLER_NAME=본인이름` / `SELLER_STORE=쿠팡스토어명`
- 완전 자동 발송: `OUTREACH_AUTO_SEND=true`
- 1688 공급사는 왕왕 채팅이라 `out\outreach\*.1688.txt` 초안을 복사해 붙여넣기

---

## 6단계 — 텔레그램 알림 (강력 추천, 5분)

1. 텔레그램에서 **@BotFather** 검색 → 대화 → `/newbot` 입력 → 봇 이름과
   아이디(끝이 `bot`) 정하기 → **봇 토큰**(`123456:AA...`) 받기
2. 텔레그램에서 **@userinfobot** 검색 → `/start` → 내 **챗 ID**(숫자) 확인
3. **방금 만든 내 봇을 검색해서 `/start`를 한 번 보낸다** (이걸 해야 봇이
   나에게 메시지를 보낼 수 있음)
4. `.env`: `TELEGRAM_BOT_TOKEN=봇토큰` / `TELEGRAM_CHAT_ID=내챗ID`
- ⚠️ 봇 토큰은 비밀값. 남에게 노출됐으면 @BotFather에서 `/revoke`로 재발급.

---

## 7단계 — 나중에 (지금은 건너뛰기)

- **Instagram Reels**: 비즈니스 계정 전환 + 페이스북 페이지 연결 + Meta 앱
  검수(`instagram_content_publish`, 수 주 소요). 유튜브 성과 난 뒤 진행.
- **YouTube Shopping 제품 태그**(영상 속 상품 아이콘): YPP 가입 + 쇼핑 자격
  충족 후 유튜브 스튜디오에서 수동 연동 (자동화 API 없음).
- **ElevenLabs**: 훅 문장만 고품질 보이스로 바꾸고 싶을 때.

---

## 최종 실행

1. `shortform` 폴더에서 **`start.bat` 더블클릭** → 브라우저 스튜디오 열림
2. (검은 창은 닫지 말 것 — 닫으면 꺼짐. 최소화만)
3. 자동으로 계속 돌리려면 스튜디오에서 **`🔁 자동 모드 시작`**
4. 하루 1~2번 **`3. 확인·승인`** 에서 만들어진 영상 보고 승인/반려

## .env 최종 점검표

| 항목 | 단계 | 필수 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 1-4 | ✅ 필수 |
| `YOUTUBE_API_KEY` | 2-3 | 자동 소싱 |
| `client_secret.json` (파일) | 3-3 | 업로드 |
| `products.yaml`의 `partners_link` | 4 | 상품 트랙 |
| `RESEND_API_KEY` 또는 `SMTP_*` | 5 | 자동 발송 |
| `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID` | 6 | 권장 |
| `SELLER_NAME`/`SELLER_STORE` | 5 | 아웃리치 |

막히는 화면이 있으면 그 화면 상태를 알려주면 그 지점부터 짚어준다.
