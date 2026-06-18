import { useEffect, useMemo, useRef, useState } from "react";
import { useGame } from "../store";
import { CHARACTER_MAP } from "../data/characters";
import { nextScriptFor, EVENT_MAP } from "../data";
import { stageOf } from "../engine/affection";
import type { Choice } from "../types";

type Action =
  | { type: "them"; text: string }
  | { type: "choices"; choices: Choice[] };

type Bubble = { from: "them" | "me"; text: string };

const TYPING_MS = 700;
const READ_MS = 450;

export default function ChatRoom() {
  const { state, activeCharacterId, applyChoice, clearScript, openEvent, goHome, advanceDay } =
    useGame();

  const character = activeCharacterId ? CHARACTER_MAP[activeCharacterId] : undefined;
  const cs = activeCharacterId ? state?.characters[activeCharacterId] : undefined;

  const script = useMemo(() => {
    if (!state || !activeCharacterId || !cs) return undefined;
    return nextScriptFor(activeCharacterId, cs.affection, cs.clearedScripts);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCharacterId]);

  const [queue, setQueue] = useState<Action[]>([]);
  const [pointer, setPointer] = useState(0);
  const [log, setLog] = useState<Bubble[]>([]);
  const [typing, setTyping] = useState(false);
  const [choices, setChoices] = useState<Choice[] | null>(null);
  const [toast, setToast] = useState<number | null>(null);
  const [done, setDone] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 스크립트로 초기 큐 구성
  useEffect(() => {
    if (!script) {
      setDone(true);
      return;
    }
    const q: Action[] = script.nodes.map((n) =>
      n.kind === "say" ? { type: "them", text: n.text } : { type: "choices", choices: n.choices },
    );
    setQueue(q);
    setPointer(0);
    setLog([]);
    setDone(false);
  }, [script]);

  // 큐 진행
  useEffect(() => {
    if (!script || queue.length === 0) return;
    if (pointer >= queue.length) {
      finalize();
      return;
    }
    const action = queue[pointer];
    if (action.type === "them") {
      setTyping(true);
      const t1 = setTimeout(() => {
        setTyping(false);
        setLog((l) => [...l, { from: "them", text: action.text }]);
        const t2 = setTimeout(() => setPointer((p) => p + 1), READ_MS);
        timers.current.push(t2);
      }, TYPING_MS);
      timers.current.push(t1);
    } else {
      setChoices(action.choices);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointer, queue]);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  // 자동 스크롤
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [log, typing, choices, done]);

  function onPick(choice: Choice) {
    if (!character || !activeCharacterId) return;
    setChoices(null);
    setLog((l) => [...l, { from: "me", text: choice.text }]);
    const delta = applyChoice(activeCharacterId, choice, character);
    setToast(delta);
    setTimeout(() => setToast(null), 900);

    // 선택 노드 다음에 상대 답장 삽입
    const replies: Action[] = choice.reply.map((t) => ({ type: "them", text: t }));
    setQueue((q) => {
      const next = [...q];
      next.splice(pointer + 1, 0, ...replies);
      return next;
    });
    setPointer((p) => p + 1);
  }

  function finalize() {
    if (!script || !activeCharacterId || done) return;
    clearScript(activeCharacterId, script.id);
    advanceDay();
    setDone(true);
  }

  if (!character) return null;
  const aff = cs?.affection ?? 0;
  const rewardEvent =
    script?.rewardEvent && !cs?.seenEvents.includes(script.rewardEvent)
      ? EVENT_MAP[script.rewardEvent]
      : undefined;

  return (
    <div className="flex h-full w-full flex-col bg-kakao">
      {/* 헤더 */}
      <header className="flex items-center gap-2 bg-kakao/90 px-3 py-2 backdrop-blur">
        <button className="px-1 text-lg" onClick={goHome}>
          ←
        </button>
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/70 text-lg">
          {character.emoji}
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold">{character.name}</div>
          <div className="text-[10px] text-gray-600">
            {stageOf(aff)} · 호감도 {aff}
          </div>
        </div>
      </header>

      {/* 상황 설명 */}
      {script && (
        <div className="px-4 py-2 text-center text-[11px] text-gray-700/80">{script.title}</div>
      )}

      {/* 대화 로그 */}
      <div ref={scrollRef} className="relative flex-1 space-y-2 overflow-y-auto px-3 pb-3">
        {log.map((b, i) =>
          b.from === "them" ? (
            <div key={i} className="flex items-end gap-2">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/70 text-base">
                {character.emoji}
              </div>
              <div className="max-w-[72%] animate-pop rounded-2xl rounded-tl-md bg-bubbleYou px-3 py-2 text-sm shadow">
                {b.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-end">
              <div className="max-w-[72%] animate-pop rounded-2xl rounded-tr-md bg-bubbleMe px-3 py-2 text-sm shadow">
                {b.text}
              </div>
            </div>
          ),
        )}

        {typing && (
          <div className="flex items-end gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/70 text-base">
              {character.emoji}
            </div>
            <div className="rounded-2xl rounded-tl-md bg-bubbleYou px-3 py-2 text-sm text-gray-400 shadow">
              <span className="inline-flex gap-1">
                <Dot /> <Dot delay="150ms" /> <Dot delay="300ms" />
              </span>
            </div>
          </div>
        )}

        {toast !== null && (
          <div className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 animate-floatHeart text-lg font-bold text-heart">
            {toast >= 0 ? `❤ +${toast}` : `💔 ${toast}`}
          </div>
        )}
      </div>

      {/* 선택지 / 종료 영역 */}
      <div className="border-t border-white/40 bg-white/60 p-3">
        {choices ? (
          <div className="flex flex-col gap-2">
            {choices.map((c, i) => (
              <button
                key={i}
                className="rounded-xl bg-white px-3 py-2 text-left text-sm shadow active:scale-[0.98]"
                onClick={() => onPick(c)}
              >
                {c.text}
              </button>
            ))}
          </div>
        ) : done ? (
          <div className="flex flex-col gap-2">
            {rewardEvent ? (
              <button
                className="rounded-xl bg-heart py-2.5 text-sm font-semibold text-white shadow active:scale-95"
                onClick={() => openEvent(rewardEvent.id)}
              >
                💗 설렘 이벤트 — {rewardEvent.title}
              </button>
            ) : (
              <p className="text-center text-xs text-gray-500">대화를 마쳤어. 또 톡하자!</p>
            )}
            <button
              className="rounded-xl bg-gray-200 py-2.5 text-sm font-semibold text-gray-600 active:scale-95"
              onClick={goHome}
            >
              채팅 목록으로
            </button>
          </div>
        ) : (
          <p className="text-center text-xs text-gray-400">…</p>
        )}
      </div>
    </div>
  );
}

function Dot({ delay = "0ms" }: { delay?: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400"
      style={{ animationDelay: delay }}
    />
  );
}
