/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          400: "#5b8def",
          500: "#3467e0",
          600: "#2650bd",
          700: "#1f3f96",
          900: "#182b63",
        },
        surface: {
          DEFAULT: "#ffffff",
          muted: "#f6f7fb",
          border: "#e4e7ee",
        },
        ink: {
          DEFAULT: "#12141c",
          muted: "#5b6272",
          faint: "#8b91a0",
        },
        good: "#1a9e5c",
        bad: "#d3402e",
        warn: "#c17d0f",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["'JetBrains Mono'", "'Cascadia Code'", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16, 24, 40, 0.06), 0 1px 3px rgba(16, 24, 40, 0.08)",
      },
    },
  },
  plugins: [],
};
