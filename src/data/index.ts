import type { DialogueScript, HeartEvent } from "../types";
import { MINJUN_SCRIPTS, MINJUN_EVENTS } from "./minjun";

export const ALL_SCRIPTS: DialogueScript[] = [...MINJUN_SCRIPTS];
export const ALL_EVENTS: HeartEvent[] = [...MINJUN_EVENTS];

export const EVENT_MAP: Record<string, HeartEvent> = Object.fromEntries(
  ALL_EVENTS.map((e) => [e.id, e]),
);

/** 특정 캐릭터의 다음 플레이 가능한 대화 찾기 (호감도/완주 기준) */
export function nextScriptFor(
  characterId: string,
  affection: number,
  cleared: string[],
): DialogueScript | undefined {
  return ALL_SCRIPTS.filter(
    (s) =>
      s.characterId === characterId &&
      !cleared.includes(s.id) &&
      affection >= s.affectionMin,
  ).sort((a, b) => a.affectionMin - b.affectionMin)[0];
}
