import { useGame } from "../store";
import { CHARACTERS, PLAYABLE_IDS } from "../data/characters";
import { stageOf } from "../engine/affection";
import { nextScriptFor } from "../data";

/** 홈 = 카톡 친구목록 + 상단 달력/시즌 (기획서 8장 핵심화면) */
export default function Home() {
  const { state, openChat, goHome } = useGame();
  if (!state) return null;

  return (
    <div className="flex h-full w-full flex-col bg-white">
      {/* 상단 바: 시즌/일자 */}
      <header className="bg-rose-400 px-4 py-3 text-white">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs opacity-80">1학년 · {state.season} 학기</div>
            <div className="text-lg font-bold">{state.player.name}의 봄날 🌸</div>
          </div>
          <div className="text-right text-xs opacity-90">
            Day {state.day}
            <div>앨범 {state.album.length}장</div>
          </div>
        </div>
      </header>

      <div className="px-4 pt-3 text-xs font-semibold text-gray-400">채팅</div>

      {/* 친구(공략 캐릭터) 목록 */}
      <ul className="flex-1 overflow-y-auto">
        {CHARACTERS.map((c) => {
          const cs = state.characters[c.id];
          const aff = cs?.affection ?? 0;
          const locked = !PLAYABLE_IDS.includes(c.id);
          const hasNew = !locked && !!nextScriptFor(c.id, aff, cs?.clearedScripts ?? []);
          return (
            <li
              key={c.id}
              className={`flex items-center gap-3 border-b border-gray-100 px-4 py-3 ${
                locked ? "opacity-40" : "active:bg-rose-50"
              }`}
              onClick={() => !locked && openChat(c.id)}
            >
              <div
                className="flex h-12 w-12 items-center justify-center rounded-2xl text-2xl"
                style={{ background: c.color + "55" }}
              >
                {locked ? "🔒" : c.emoji}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{c.name}</span>
                  <span className="text-[10px] text-gray-400">{c.archetype}</span>
                </div>
                <div className="truncate text-xs text-gray-500">{c.blurb}</div>
              </div>
              {!locked && (
                <div className="text-right">
                  <div className="text-[10px] text-rose-400">{stageOf(aff)}</div>
                  <div className="flex items-center gap-1 text-xs">
                    <span className="text-heart">❤</span>
                    {aff}
                  </div>
                  {hasNew && (
                    <span className="mt-0.5 inline-block rounded-full bg-rose-400 px-1.5 text-[9px] text-white">
                      new
                    </span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <footer className="flex items-center justify-around border-t border-gray-100 py-2 text-xs text-gray-400">
        <button className="font-semibold text-rose-400" onClick={goHome}>
          💬 채팅
        </button>
        <span>📅 일정</span>
        <span>🖼️ 앨범</span>
        <span>⚙️ 설정</span>
      </footer>
    </div>
  );
}
