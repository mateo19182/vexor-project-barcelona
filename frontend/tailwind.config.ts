import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Backgrounds
        'bg-base':     '#09090B',
        'bg-surface':  '#111113',
        'bg-elevated': '#19191C',
        'bg-overlay':  '#222225',
        // Borders
        'border-subtle':  '#27272A',
        'border-default': '#3F3F46',
        'border-strong':  '#52525B',
        // Text
        'text-primary':   '#FAFAFA',
        'text-secondary': '#A1A1AA',
        'text-tertiary':  '#52525B',
        'text-inverse':   '#09090B',
        // Accents (monochrome)
        'accent-primary': '#FAFAFA',
        'accent-muted':   '#A1A1AA',
        'accent-dim':     '#71717A',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      ringColor: {
        DEFAULT: '#FAFAFA',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config
