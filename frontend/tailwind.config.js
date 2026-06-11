/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        athena: {
          bg: '#0a0e14',
          panel: '#11161f',
          accent: '#5eead4',
          accent2: '#818cf8',
        },
      },
    },
  },
  plugins: [],
}
