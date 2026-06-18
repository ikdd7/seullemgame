# 설렘 100% 🌸 (Phase 1 MVP)

카톡형 대화로 호감도를 쌓고, 데이트·설렘 이벤트로 사귀는 **고등학교 3년 청춘 연애 시뮬레이션**.
전체 기획은 [`docs/dating-sim/기획서.md`](../docs/dating-sim/기획서.md) 참고.

## 이번 MVP에 들어간 것 (수직 슬라이스)

- **타이틀 → 새 게임/이어하기** (주인공 이름 설정, localStorage 세이브)
- **홈 = 카톡 친구목록** + 시즌/호감도/관계단계 표시
- **카톡 채팅방** — 말풍선, "입력 중…" 타이핑 연출, 답장 선택지, 호감도 ❤ 토스트
- **호감도 엔진** — 선택지 태그가 캐릭터 취향과 맞으면 보너스, 단계(남남→친구→썸→고백가능→연인) 산출
- **설렘 이벤트** — CG 자리(placeholder) + 비주얼노벨 대사 진행 → 앨범 저장
- 첫 공략 캐릭터 **민준(소꿉친구)** · 1학년 1시즌 대화 2편 + 우산 이벤트

> 일러스트/배경음은 아직 placeholder(이모지·그라데이션). 로직부터 검증하는 단계.

## 실행

```bash
cd game
npm install
npm run dev      # 개발 서버 (브라우저에서 열기)
npm run build    # 타입체크 + 프로덕션 빌드
npm test         # 호감도 엔진 유닛 테스트(vitest)
```

## 구조

```
game/src/
├── types.ts                 # 도메인 타입 (Character, DialogueScript, HeartEvent, GameState)
├── store.ts                 # Zustand 스토어 + 세이브/로드 + 호감도 적용
├── engine/affection.ts      # 호감도 → 단계 변환 / 선택지 가중치
├── data/
│   ├── characters.ts        # 공략 캐릭터 정의
│   ├── minjun.ts            # 민준 대사 스크립트 + 설렘 이벤트 (데이터로 분리)
│   └── index.ts             # 스크립트/이벤트 조회 헬퍼
└── components/
    ├── Title.tsx            # 타이틀
    ├── Home.tsx             # 카톡 친구목록 홈
    ├── ChatRoom.tsx         # ★ 카톡 채팅 (게임의 심장)
    └── HeartEventView.tsx   # 설렘 이벤트(비주얼노벨)
```

## 대사 추가하는 법 (코드 없이 콘텐츠 확장)

`src/data/minjun.ts`의 `MINJUN_SCRIPTS` 배열에 객체 하나를 더하면 새 대화가 생긴다.
`affectionMin`으로 해금 조건, `nodes`로 대사/선택지, `rewardEvent`로 설렘 이벤트 연결.
새 캐릭터는 `characters.ts`에 추가하고 `PLAYABLE_IDS`에 id를 넣으면 잠금이 풀린다.

## 다음 (Phase 2 예정)

캐릭터 4명 확장 · 데이트 장소 시스템 · 갤러리 화면 · 삼각관계/질투 분기 · 멀티 엔딩.
