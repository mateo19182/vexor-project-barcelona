import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Backgrounds
        'bg-base':     '#080B12',
        'bg-surface':  '#0E1320',
        'bg-elevated': '#141925',
        'bg-overlay':  '#1A2133',
        // Borders
        'border-subtle':  '#1E2A3A',
        'border-default': '#263345',
        'border-strong':  '#344560',
        // Text
        'text-primary':   '#E8EDF5',
        'text-secondary': '#8A9BB8',
        'text-tertiary':  '#4A5A72',
        'text-inverse':   '#080B12',
        // Accents
        'accent-cyan':    '#00E5FF',
        'accent-violet':  '#7C3AED',
        'accent-emerald': '#10B981',
        'accent-amber':   '#F59E0B',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      ringColor: {
        DEFAULT: '#00E5FF',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config
