import type { DialogueScript, HeartEvent } from "../types";

/**
 * 민준 — 1학년 1시즌 대화 스크립트.
 * 기획자가 코드 없이 대사를 늘릴 수 있도록 데이터로 분리(기획서 9장).
 */
export const MINJUN_SCRIPTS: DialogueScript[] = [
  {
    id: "minjun_1_1_intro",
    characterId: "minjun",
    season: "1-1",
    affectionMin: 0,
    title: "입학 첫날, 옆자리에 앉은 남자애가 말을 걸어왔다.",
    nodes: [
      { kind: "say", from: "them", text: "야 너 이 반 맞지? ㅋㅋ" },
      { kind: "say", from: "them", text: "나 민준. 1년 동안 잘 지내보자~ 🌻" },
      {
        kind: "choices",
        choices: [
          {
            text: "응! 나도 잘 부탁해 😊",
            affection: 5,
            tag: "솔직",
            reply: ["오 첫인상 좋은데?", "우리 짝꿍이니까 자주 보겠다 ㅋㅋ"],
          },
          {
            text: "...누구세요?",
            affection: 1,
            tag: "장난",
            reply: ["헐 상처ㅋㅋㅋ", "방금 이름 말했잖아 민준이라고!"],
          },
          {
            text: "(그냥 끄덕인다)",
            affection: 2,
            reply: ["수줍음이 많구나~", "괜찮아 천천히 친해지자 :)"],
          },
        ],
      },
      { kind: "say", from: "them", text: "참, 폰 번호 줄래? 알림장 같은 거 공유하게 ㅎㅎ" },
      {
        kind: "choices",
        choices: [
          {
            text: "좋아, 카톡 추가했어!",
            affection: 6,
            tag: "다정",
            reply: ["굿굿 ㅋㅋ", "이제 우리 톡 친구다 😎"],
          },
          {
            text: "급발진 아니야? ㅋㅋ",
            affection: 3,
            tag: "장난",
            reply: ["아니거든ㅋㅋㅋ 순수한 학업 목적임", "...반은 진심이지만"],
          },
        ],
      },
    ],
  },
  {
    id: "minjun_1_1_rain",
    characterId: "minjun",
    season: "1-1",
    affectionMin: 20,
    title: "방과후, 갑자기 비가 쏟아졌다. 민준에게서 톡이 왔다.",
    nodes: [
      { kind: "say", from: "them", text: "헐 밖에 비 봤어?? 🌧️" },
      { kind: "say", from: "them", text: "너 우산 있어?" },
      {
        kind: "choices",
        choices: [
          {
            text: "없는데... 어떡하지 ㅠㅠ",
            affection: 4,
            reply: ["기다려봐", "나 우산 하나 있어. 같이 쓸래?"],
          },
          {
            text: "어 같이 쓸래? 😳",
            affection: 8,
            tag: "솔직",
            reply: ["오... 적극적인데? ㅋㅋ", "콜. 정문에서 봐!"],
          },
          {
            text: "너 우산 뺏어야지 ㅋㅋ",
            affection: 2,
            tag: "장난",
            reply: ["야 그럼 넌 어쩌고ㅋㅋㅋ", "에이 그냥 같이 쓰자"],
          },
        ],
      },
      { kind: "say", from: "them", text: "근데 우산이 좀 작아서... 가까이 붙어야 될 듯 ㅎㅎ;;" },
      {
        kind: "choices",
        choices: [
          {
            text: "괜찮아, 어깨 정도는 ㅎㅎ",
            affection: 7,
            tag: "다정",
            reply: ["...어 그래", "(왜 갑자기 심장이 빨리 뛰지)"],
          },
          {
            text: "거리 유지! 🙅",
            affection: 1,
            reply: ["아 차갑네ㅋㅋ", "비 다 맞겠다 너ㅋㅋㅋ"],
          },
        ],
      },
    ],
    rewardEvent: "minjun_umbrella",
  },
];

/** 민준 — 설렘 이벤트(CG 자리 placeholder) */
export const MINJUN_EVENTS: HeartEvent[] = [
  {
    id: "minjun_umbrella",
    characterId: "minjun",
    title: "하나의 우산 아래",
    bg: "linear-gradient(160deg,#9fb6cf,#5d7a99)",
    emoji: "☔",
    affection: 10,
    lines: [
      { speaker: "나레이션", text: "작은 우산 하나에 둘이 들어가니, 어깨가 자꾸 닿았다." },
      { speaker: "민준", text: "야, 너 비 안 맞게 이쪽으로 더 와." },
      { speaker: "나레이션", text: "민준이 우산을 내 쪽으로 기울였다. 자기 어깨가 다 젖는 줄도 모르고." },
      { speaker: "나", text: "(...너 다 젖잖아.)" },
      { speaker: "민준", text: "뭐 어때. 너만 안 젖으면 됐지." },
      { speaker: "나레이션", text: "빗소리 사이로, 심장 뛰는 소리가 유난히 크게 들렸다." },
    ],
  },
];
