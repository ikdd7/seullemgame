import { useState } from "react";
import { useGame } from "../store";
import { EVENT_MAP } from "../data";
import { CHARACTER_MAP } from "../data/characters";

/** 설렘 이벤트 = CG(placeholder) + 한 줄씩 진행되는 비주얼노벨 (기획서 5장) */
export default function HeartEventView() {
  const { activeEventId, completeEvent, goHome } = useGame();
  const ev = activeEventId ? EVENT_MAP[activeEventId] : undefined;
  const [i, setI] = useState(0);
  const [finished, setFinished] = useState(false);

  if (!ev) return null;
  const event = ev;
  const character = CHARACTER_MAP[event.characterId];
  const line = event.lines[i];
  const isNarration = line.speaker === "나레이션";

  function next() {
    if (i < event.lines.length - 1) {
      setI(i + 1);
    } else if (!finished) {
      completeEvent(event.characterId, event.id, event.affection);
      setFinished(true);
    }
  }

  return (
    <div className="relative flex h-full w-full flex-col" style={{ background: ev.bg }}>
      {/* CG 자리(placeholder): 대형 이모지 + 타이틀 */}
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-white">
        <div className="text-[7rem] drop-shadow-lg">{ev.emoji}</div>
        <div className="rounded-full bg-black/25 px-4 py-1 text-sm">{ev.title}</div>
      </div>

      {/* 대사창 */}
      {!finished ? (
        <button
          className="m-3 rounded-2xl bg-black/60 p-4 text-left text-white backdrop-blur active:bg-black/70"
          onClick={next}
        >
          {!isNarration && (
            <div className="mb-1 text-sm font-bold text-heart">
              {line.speaker === "나" ? "나" : character?.name ?? line.speaker}
            </div>
          )}
          <p className={`text-sm leading-relaxed ${isNarration ? "italic text-white/80" : ""}`}>
            {line.text}
          </p>
          <div className="mt-2 text-right text-[10px] text-white/50">
            탭하여 계속 ({i + 1}/{ev.lines.length})
          </div>
        </button>
      ) : (
        <div className="m-3 flex flex-col gap-2 rounded-2xl bg-white/90 p-4">
          <div className="text-center text-sm font-semibold text-heart">
            💗 추억이 앨범에 저장됐어 (+{ev.affection})
          </div>
          <button
            className="rounded-xl bg-rose-400 py-2.5 text-sm font-semibold text-white active:scale-95"
            onClick={goHome}
          >
            채팅 목록으로
          </button>
        </div>
      )}
    </div>
  );
}
