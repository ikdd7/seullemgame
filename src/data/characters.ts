import type { Character } from "../types";

/** 공략 캐릭터 정의 (MVP는 민준 1명, 나머지는 잠금 표시용) */
export const CHARACTERS: Character[] = [
  {
    id: "minjun",
    name: "민준",
    archetype: "소꿉친구 · 햇살남",
    blurb: "옆자리 짝꿍. 늘 챙겨주지만 솔직한 감정 표현엔 약하다.",
    prefTags: ["솔직", "다정", "장난"],
    emoji: "🌻",
    color: "#ffcf5c",
  },
  {
    id: "seojun",
    name: "서준",
    archetype: "츤데레 · 모범생",
    blurb: "차갑지만 알고 보면 다정. (잠금)",
    prefTags: ["인정", "차분"],
    emoji: "📘",
    color: "#7aa7ff",
  },
  {
    id: "haru",
    name: "하루",
    archetype: "인기남 · 밴드부",
    blurb: "학교 스타. 가벼워 보이지만 진심. (잠금)",
    prefTags: ["진심", "유머"],
    emoji: "🎸",
    color: "#ff8fb1",
  },
];

export const CHARACTER_MAP: Record<string, Character> = Object.fromEntries(
  CHARACTERS.map((c) => [c.id, c]),
);

/** MVP에서 실제 플레이 가능한 캐릭터 id */
export const PLAYABLE_IDS = ["minjun"];
