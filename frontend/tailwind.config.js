/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Dark-mode categorical + status steps from the studio data-viz palette,
        // validated (all-pairs CVD + contrast) against the void surface #060608.
        series: {
          blue: '#3987e5',
          green: '#008300',
          magenta: '#d55181',
          yellow: '#c98500',
          aqua: '#199e70',
          orange: '#d95926',
          violet: '#9085e9',
          red: '#e66767',
        },
        status: {
          good: '#0ca30c',
          warning: '#fab219',
          serious: '#ec835a',
          critical: '#d03b3b',
        },
        void: '#060608',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'SF Pro Display',
          'system-ui',
          'Segoe UI',
          'sans-serif',
        ],
      },
      transitionTimingFunction: {
        premium: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
}
