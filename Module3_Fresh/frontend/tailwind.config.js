/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        ink: { 950:'#0a0b0d', 900:'#101216', 850:'#15181d', 800:'#1b1f26',
               700:'#2a2f38', 600:'#3d434e', 500:'#5a616e', 400:'#868d9a',
               300:'#b3b9c4', 200:'#d6dae1', 100:'#eceef2', 50:'#f7f8fa' },
        accent: { DEFAULT:'#4f7cff', soft:'#7d9dff', dim:'#2d4ba8' },
        ok: '#3fbf7f', warn: '#e0a33e', err: '#e05252',
      },
      animation: {
        'fade-up': 'fadeUp .45s cubic-bezier(.16,1,.3,1) both',
        'pulse-soft': 'pulseSoft 1.8s ease-in-out infinite',
        'bar': 'bar 1.4s ease-in-out infinite',
      },
      keyframes: {
        fadeUp: { '0%': { opacity:'0', transform:'translateY(10px)' },
                  '100%': { opacity:'1', transform:'translateY(0)' } },
        pulseSoft: { '0%,100%': { opacity:'1' }, '50%': { opacity:'.45' } },
        bar: { '0%': { transform:'translateX(-100%)' }, '100%': { transform:'translateX(400%)' } },
      },
    },
  },
  plugins: [],
}
