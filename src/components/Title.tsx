import { useState } from "react";
import { useGame } from "../store";

export default function Title() {
  const { newGame, load, hasSave } = useGame();
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"menu" | "new">("menu");

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-6 bg-gradient-to-b from-pink-100 to-rose-200 px-8 text-center">
      <div className="text-6xl">🌸</div>
      <h1 className="text-3xl font-bold text-rose-500">설렘 100%</h1>
      <p className="-mt-3 text-sm text-rose-400">카톡으로 시작되는 우리의 3년</p>

      {mode === "menu" ? (
        <div className="mt-4 flex w-full max-w-xs flex-col gap-3">
          <button
            className="rounded-2xl bg-rose-400 py-3 font-semibold text-white shadow active:scale-95"
            onClick={() => setMode("new")}
          >
            새 게임
          </button>
          <button
            className="rounded-2xl bg-white py-3 font-semibold text-rose-400 shadow disabled:opacity-40 active:scale-95"
            disabled={!hasSave()}
            onClick={() => load()}
          >
            이어하기
          </button>
        </div>
      ) : (
        <div className="mt-4 flex w-full max-w-xs flex-col gap-3">
          <input
            className="rounded-2xl border border-rose-200 px-4 py-3 text-center outline-none focus:border-rose-400"
            placeholder="주인공 이름을 정해줘"
            value={name}
            maxLength={8}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            className="rounded-2xl bg-rose-400 py-3 font-semibold text-white shadow active:scale-95"
            onClick={() => newGame(name.trim())}
          >
            입학하기 ✏️
          </button>
          <button className="text-sm text-rose-400" onClick={() => setMode("menu")}>
            ← 뒤로
          </button>
        </div>
      )}
    </div>
  );
}
