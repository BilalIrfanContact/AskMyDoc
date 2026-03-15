import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: "#0f1b2d",
        mist: "#f4f6f9",
        tide: "#2b6cb0",
        coral: "#f97316",
        night: "#0b1020",
        slate: "#1c2638"
      },
      boxShadow: {
        glow: "0 12px 40px rgba(15, 27, 45, 0.18)",
        glowDark: "0 12px 40px rgba(2, 6, 23, 0.6)"
      },
      backgroundImage: {
        "hero-gradient": "radial-gradient(circle at top, rgba(255,255,255,0.9), rgba(244,246,249,0.75), rgba(214,228,255,0.6))",
        "hero-gradient-dark": "radial-gradient(circle at top, rgba(30,41,59,0.9), rgba(15,23,42,0.85), rgba(2,6,23,0.9))"
      }
    }
  },
  plugins: []
};

export default config;
