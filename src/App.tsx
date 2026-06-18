import { useGame } from "./store";
import Title from "./components/Title";
import Home from "./components/Home";
import ChatRoom from "./components/ChatRoom";
import HeartEventView from "./components/HeartEventView";

export default function App() {
  const view = useGame((s) => s.view);

  return (
    // 모바일 세로 프레임 (기획서 1장: 세로 화면)
    <div className="relative h-[100dvh] w-full max-w-[430px] overflow-hidden bg-white shadow-2xl sm:my-4 sm:h-[860px] sm:rounded-[2rem]">
      {view === "title" && <Title />}
      {view === "home" && <Home />}
      {view === "chat" && <ChatRoom />}
      {view === "event" && <HeartEventView />}
    </div>
  );
}
