import type { Character, Choice, Stage } from "../types";

/** 호감도 구간 → 관계 단계 (기획서 3.1) */
export function stageOf(affection: number): Stage {
  if (affection >= 90) return "연인";
  if (affection >= 70) return "고백가능";
  if (affection >= 45) return "썸";
  if (affection >= 20) return "친구";
  return "남남";
}

/** 0~100 클램프 */
export function clamp(n: number): number {
  return Math.max(0, Math.min(100, n));
}

/**
 * 선택지가 캐릭터 취향과 맞으면 보너스, 어긋나면 패널티.
 * 기획서 3.2: 성격/취향 태그 매칭 시 +, 어긋나면 약한 −.
 */
export function affectionDelta(choice: Choice, character: Character): number {
  let delta = choice.affection;
  if (choice.tag) {
    if (character.prefTags.includes(choice.tag)) delta += 3;
    else if (choice.affection < 0) delta -= 1; // 안 맞는데 깐족 → 더 손해
  }
  return delta;
}
