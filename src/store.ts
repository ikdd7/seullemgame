import { create } from "zustand";
import type { Character, Choice, GameState } from "./types";
import { affectionDelta, clamp } from "./engine/affection";

const SAVE_KEY = "seollem100.save.v1";

function freshState(name: string): GameState {
  return {
    player: { name: name || "주인공" },
    season: "1-1",
    day: 1,
    characters: {
      minjun: { affection: 0, clearedScripts: [], seenEvents: [] },
    },
    flags: {},
    album: [],
  };
}

export type View = "title" | "home" | "chat" | "event";

interface Store {
  state: GameState | null;
  view: View;
  activeCharacterId: string | null;
  activeEventId: string | null;

  // lifecycle
  newGame: (name: string) => void;
  load: () => boolean;
  save: () => void;
  hasSave: () => boolean;

  // navigation
  goHome: () => void;
  openChat: (characterId: string) => void;
  openEvent: (eventId: string) => void;

  // gameplay
  applyChoice: (characterId: string, choice: Choice, character: Character) => number;
  clearScript: (characterId: string, scriptId: string) => void;
  completeEvent: (characterId: string, eventId: string, affection: number) => void;
  advanceDay: () => void;
}

export const useGame = create<Store>((set, get) => ({
  state: null,
  view: "title",
  activeCharacterId: null,
  activeEventId: null,

  newGame: (name) => {
    const state = freshState(name);
    set({ state, view: "home" });
    localStorage.setItem(SAVE_KEY, JSON.stringify(state));
  },

  load: () => {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return false;
    try {
      const state = JSON.parse(raw) as GameState;
      set({ state, view: "home" });
      return true;
    } catch {
      return false;
    }
  },

  save: () => {
    const { state } = get();
    if (state) localStorage.setItem(SAVE_KEY, JSON.stringify(state));
  },

  hasSave: () => localStorage.getItem(SAVE_KEY) !== null,

  goHome: () => set({ view: "home", activeCharacterId: null, activeEventId: null }),
  openChat: (characterId) => set({ view: "chat", activeCharacterId: characterId }),
  openEvent: (eventId) => set({ view: "event", activeEventId: eventId }),

  applyChoice: (characterId, choice, character) => {
    const delta = affectionDelta(choice, character);
    set((s) => {
      if (!s.state) return s;
      const cs = s.state.characters[characterId];
      const next = { ...cs, affection: clamp(cs.affection + delta) };
      return {
        state: {
          ...s.state,
          characters: { ...s.state.characters, [characterId]: next },
        },
      };
    });
    return delta;
  },

  clearScript: (characterId, scriptId) => {
    set((s) => {
      if (!s.state) return s;
      const cs = s.state.characters[characterId];
      if (cs.clearedScripts.includes(scriptId)) return s;
      const next = { ...cs, clearedScripts: [...cs.clearedScripts, scriptId] };
      return {
        state: {
          ...s.state,
          characters: { ...s.state.characters, [characterId]: next },
        },
      };
    });
    get().save();
  },

  completeEvent: (characterId, eventId, affection) => {
    set((s) => {
      if (!s.state) return s;
      const cs = s.state.characters[characterId];
      const seen = cs.seenEvents.includes(eventId)
        ? cs.seenEvents
        : [...cs.seenEvents, eventId];
      const album = s.state.album.includes(eventId)
        ? s.state.album
        : [...s.state.album, eventId];
      const next = { ...cs, seenEvents: seen, affection: clamp(cs.affection + affection) };
      return {
        state: {
          ...s.state,
          album,
          characters: { ...s.state.characters, [characterId]: next },
        },
      };
    });
    get().save();
  },

  advanceDay: () => {
    set((s) => (s.state ? { state: { ...s.state, day: s.state.day + 1 } } : s));
    get().save();
  },
}));
