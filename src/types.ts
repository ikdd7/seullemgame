// 게임 도메인 타입 정의 — 기획서 10장(데이터 모델) 기준

/** 관계 단계 */
export type Stage = "남남" | "친구" | "썸" | "고백가능" | "연인";

/** 공략 캐릭터 */
export interface Character {
  id: string;
  name: string;
  archetype: string;
  /** 프로필 한 줄 */
  blurb: string;
  /** 좋아하는 말투/화제 태그 — 선택지 tag와 매칭되면 보너스 */
  prefTags: string[];
  /** 아바타 대신 쓰는 이모지(아트 전 placeholder) */
  emoji: string;
  /** 말풍선/테마 색 */
  color: string;
}

/** 대화 선택지 */
export interface Choice {
  text: string;
  /** 기본 호감도 증감 */
  affection: number;
  /** 이 선택지의 성향 태그 (캐릭터 prefTags와 매칭 시 보너스) */
  tag?: string;
  /** 선택 후 상대 반응 메시지(여러 줄 가능) */
  reply: string[];
}

/** 대화 노드: 상대의 말 또는 나의 선택 */
export type DialogueNode =
  | { kind: "say"; from: "them"; text: string }
  | { kind: "choices"; choices: Choice[] };

/** 한 편의 대화(채팅 세션) */
export interface DialogueScript {
  id: string;
  characterId: string;
  season: string;
  /** 해금 최소 호감도 */
  affectionMin: number;
  /** 채팅방 상단 상황 설명 */
  title: string;
  nodes: DialogueNode[];
  /** 완주 시 해금되는 설렘 이벤트 id (옵션) */
  rewardEvent?: string;
}

/** 설렘 이벤트(CG + 비주얼노벨 연출) */
export interface HeartEvent {
  id: string;
  characterId: string;
  title: string;
  /** 배경 그라데이션(아트 전 placeholder) */
  bg: string;
  /** 대표 이모지 */
  emoji: string;
  /** 한 줄씩 진행되는 나레이션/대사 */
  lines: { speaker: string; text: string }[];
  /** 이벤트 완료 시 추가 호감도 */
  affection: number;
}

/** 캐릭터별 진행 상태 */
export interface CharacterState {
  affection: number;
  /** 완주한 대화 id */
  clearedScripts: string[];
  /** 본 설렘 이벤트 id */
  seenEvents: string[];
}

/** 전체 세이브 데이터 */
export interface GameState {
  player: { name: string };
  /** 현재 시즌 키 ("1-1" ...) */
  season: string;
  /** 진행 일수(턴) */
  day: number;
  characters: Record<string, CharacterState>;
  /** 분기 플래그 */
  flags: Record<string, boolean>;
  /** 획득한 CG(앨범) */
  album: string[];
}
