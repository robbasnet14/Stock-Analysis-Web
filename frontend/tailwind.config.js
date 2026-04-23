/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#ecfeff",
          100: "#cffafe",
          400: "#22d3ee",
          500: "#06b6d4",
          700: "#0e7490"
        }
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(34, 211, 238, 0.2), 0 10px 30px rgba(6, 182, 212, 0.12)"
      }
    }
  },
  plugins: []
};
