/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ember: {
          50: "#fff7ed",
          300: "#ffb265",
          400: "#ff8c3b",
          500: "#ff5a1f",
          600: "#e23f12",
          700: "#b22e0e",
        },
        ops: {
          900: "#05080f",
          850: "#080d18",
          800: "#0b1322",
          700: "#101b30",
          600: "#1a2742",
        },
        routeblue: "#38bdf8",
      },
      fontFamily: {
        display: ["Rajdhani", "Inter", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "0 0 18px rgba(56,189,248,0.45)",
        fire: "0 0 22px rgba(255,90,31,0.5)",
        panel: "0 8px 32px rgba(0,0,0,0.55)",
      },
      keyframes: {
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
        slideUp: {
          from: { transform: "translateY(14px)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        shimmer: {
          from: { backgroundPosition: "0% 0%" },
          to: { backgroundPosition: "200% 0%" },
        },
      },
      animation: {
        pulseSoft: "pulseSoft 2.2s ease-in-out infinite",
        slideUp: "slideUp 0.35s ease-out both",
        shimmer: "shimmer 3.5s linear infinite",
      },
    },
  },
  plugins: [],
};
