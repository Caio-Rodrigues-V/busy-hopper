/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          bg: "#0B0F19",      // Sleek space black
          card: "#131C2E",    // Deep midnight navy
          border: "#1E2D4A",  // Metallic blue/gray
          text: "#F3F4F6",    // Crisp off-white
          muted: "#9CA3AF"    // Cool gray
        },
        brand: {
          primary: "#3B82F6",   // Vibrant Blue
          secondary: "#10B981", // Emerald Green
          accent: "#8B5CF6",    // Electric Violet
          danger: "#EF4444"     // Rose Red
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
