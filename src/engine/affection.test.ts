import { describe, it, expect } from "vitest";
import { stageOf, clamp, affectionDelta } from "./affection";
import type { Character, Choice } from "../types";

const minjun: Character = {
  id: "minjun",
  name: "민준",
  archetype: "소꿉친구",
  blurb: "",
  prefTags: ["솔직", "다정"],
  emoji: "🌻",
  color: "#fff",
};

describe("stageOf", () => {
  it("maps affection ranges to relationship stages", () => {
    expect(stageOf(0)).toBe("남남");
    expect(stageOf(19)).toBe("남남");
    expect(stageOf(20)).toBe("친구");
    expect(stageOf(45)).toBe("썸");
    expect(stageOf(70)).toBe("고백가능");
    expect(stageOf(90)).toBe("연인");
    expect(stageOf(100)).toBe("연인");
  });
});

describe("clamp", () => {
  it("keeps affection within 0..100", () => {
    expect(clamp(-5)).toBe(0);
    expect(clamp(120)).toBe(100);
    expect(clamp(50)).toBe(50);
  });
});

describe("affectionDelta", () => {
  it("adds bonus when choice tag matches character preference", () => {
    const c: Choice = { text: "", affection: 5, tag: "솔직", reply: [] };
    expect(affectionDelta(c, minjun)).toBe(8); // 5 + 3
  });

  it("does not bonus when tag is not preferred", () => {
    const c: Choice = { text: "", affection: 5, tag: "장난", reply: [] };
    expect(affectionDelta(c, minjun)).toBe(5);
  });

  it("extra penalty when a non-preferred negative choice is picked", () => {
    const c: Choice = { text: "", affection: -1, tag: "장난", reply: [] };
    expect(affectionDelta(c, minjun)).toBe(-2); // -1 - 1
  });

  it("no tag means raw affection", () => {
    const c: Choice = { text: "", affection: 2, reply: [] };
    expect(affectionDelta(c, minjun)).toBe(2);
  });
});
