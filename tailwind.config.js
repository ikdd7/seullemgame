/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        kakao: "#b2c7da", // 카톡 채팅방 배경(파랑)
        bubbleYou: "#ffffff",
        bubbleMe: "#fef01b", // 카톡 노랑
        heart: "#ff6b8a",
      },
      fontFamily: {
        sans: ["'Pretendard'", "'Apple SD Gothic Neo'", "sans-serif"],
      },
      keyframes: {
        pop: { "0%": { transform: "scale(0.9)", opacity: "0" }, "100%": { transform: "scale(1)", opacity: "1" } },
        floatHeart: { "0%": { transform: "translateY(0)", opacity: "1" }, "100%": { transform: "translateY(-40px)", opacity: "0" } },
      },
      animation: {
        pop: "pop 0.15s ease-out",
        floatHeart: "floatHeart 0.9s ease-out forwards",
      },
    },
  },
  plugins: [],
};
