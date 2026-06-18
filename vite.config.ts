import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages 프로젝트 사이트(https://ikdd7.github.io/seullemgame/)에 맞춰
// 프로덕션 빌드에서만 base 경로를 저장소명으로 설정한다.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/seullemgame/" : "/",
  plugins: [react()],
  test: {
    environment: "node",
  },
}));
