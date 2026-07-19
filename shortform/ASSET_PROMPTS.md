# 숏폼 이미지 에셋 — ChatGPT 생성 프롬프트 모음

ChatGPT(이미지 생성)로 아래 에셋을 만들어 `shortform/assets/`에 지정된
파일명으로 저장한다. 공통 규칙:

- **투명 배경 PNG** 필수 ("transparent background, PNG" 명시).
- 오버레이 에셋은 1080x1920 캔버스 기준 실사용 크기로 요청 (아래 명기).
- 텍스트가 들어가는 에셋은 글자를 비워달라고 요청 — 텍스트는 파이프라인이
  ASS 자막으로 얹는다 (이미지 생성 한글 타이포는 깨지기 쉬움).
- 한 에셋당 3~4 변형을 뽑고 가장 깨끗한 것 채택. 스타일 일관성을 위해
  첫 채택본을 이후 프롬프트에 참조 이미지로 첨부.

## 1. 자막 강조 박스 — `subtitle-box-v1.png` (900x220)

> A clean rounded-rectangle speech box for video subtitles, dark
> semi-transparent charcoal fill with a subtle white inner glow border,
> slightly tilted -2 degrees, no text inside, flat modern Korean
> variety-show caption style, transparent background, PNG, 900x220.

## 2. 리액션 스티커 세트 — `sticker-{laugh,shock,fire,clap}-v1.png` (각 320x320)

> A bold cartoon sticker of [a laughing face with tears / a shocked face /
> a flame / clapping hands], thick white outline, vivid colors, Korean
> web-toon sticker style, no text, transparent background, PNG, 320x320.

## 3. 채널 로고 워터마크 — `logo-badge-v1.png` (240x240)

> A minimal circular channel badge logo, dark navy circle with a subtle
> gradient rim, abstract play-button motif in the center, premium tech
> feel, no letters, transparent background, PNG, 240x240.

## 4. 구독 유도 배지 — `subscribe-badge-v1.png` (520x160)

> A glossy red rounded pill button in YouTube subscribe style with a small
> bell icon on the right side, empty label area (no text), slight 3D pop,
> transparent background, PNG, 520x160.

## 5. 훅 타이틀 프레임 — `hook-frame-v1.png` (1080x480)

> A dynamic top-of-screen title frame for vertical short-form video:
> angled dark banner with yellow accent slash marks on both ends, empty
> center for text, energetic Korean entertainment show opening style,
> transparent background, PNG, 1080x480.

## 6. 출처 표기 바 — `credit-bar-v1.png` (1080x90)

> A thin minimal lower bar for source attribution, dark 70% opacity,
> small info icon on the left, empty text area, unobtrusive, transparent
> background, PNG, 1080x90.

CC-BY 소스 영상에서 M4가 이 바 위에 출처 텍스트를 자동 삽입한다.

## 7. 카테고리 컬러 태그 — `tag-{meme,tech,sports,politics}-v1.png` (280x96)

> A small rounded category tag chip, [soft violet / orange / deep blue /
> steel gray] fill with subtle diagonal texture, empty label area,
> transparent background, PNG, 280x96.

## 8. 아웃트로 CTA 카드 — `outro-card-v1.png` (1080x720)

> An end-card panel for vertical video: dark gradient panel with two empty
> rounded placeholder slots (one wide button shape, one square thumbnail
> frame), subtle particle accents, premium dark tech aesthetic, no text,
> transparent background, PNG, 1080x720.

## 체크리스트 (에셋 반입 전)

- [ ] 배경 완전 투명 확인 (흰 배경에 올려 경계 얼룩 없는지)
- [ ] 지정 파일명·해상도 준수
- [ ] 스타일 톤 일관 (첫 채택본과 나란히 비교)
- [ ] 실기기 미리보기: 1080x1920 캔버스에 올려 세이프존 침범 여부 확인
