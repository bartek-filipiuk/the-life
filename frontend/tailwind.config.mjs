/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        void: '#0a0a0f',
        alive: '#00ff88',
        cost: '#ff6b6b',
        info: '#6b9fff',
        creative: '#c084fc',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      animation: {
        pulse: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow-alive': 'glow-alive 2s ease-in-out infinite alternate',
        'glow-cost': 'glow-cost 2s ease-in-out infinite alternate',
        'terminal-blink': 'terminal-blink 1s step-end infinite',
        'fade-in': 'fade-in 0.5s ease-out',
        'slide-up': 'slide-up 0.5s ease-out',
      },
      keyframes: {
        'glow-alive': {
          '0%': { boxShadow: '0 0 5px #00ff88, 0 0 10px #00ff8833' },
          '100%': { boxShadow: '0 0 20px #00ff88, 0 0 40px #00ff8855' },
        },
        'glow-cost': {
          '0%': { boxShadow: '0 0 5px #ff6b6b, 0 0 10px #ff6b6b33' },
          '100%': { boxShadow: '0 0 20px #ff6b6b, 0 0 40px #ff6b6b55' },
        },
        'terminal-blink': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      boxShadow: {
        'glow-alive': '0 0 15px #00ff8855, 0 0 30px #00ff8822',
        'glow-cost': '0 0 15px #ff6b6b55, 0 0 30px #ff6b6b22',
        'glow-info': '0 0 15px #6b9fff55, 0 0 30px #6b9fff22',
        'glow-creative': '0 0 15px #c084fc55, 0 0 30px #c084fc22',
      },
    },
  },
  plugins: [],
};
