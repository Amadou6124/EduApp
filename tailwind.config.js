/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './apps/**/*.py',
    './static/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Manrope', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        'xs':   ['0.75rem',  { lineHeight: '1rem',    letterSpacing: '0.01em' }],
        'sm':   ['0.875rem', { lineHeight: '1.25rem', letterSpacing: '0.01em' }],
        'base': ['1rem',     { lineHeight: '1.5rem',  letterSpacing: '0' }],
        'lg':   ['1.125rem', { lineHeight: '1.75rem', letterSpacing: '-0.01em' }],
        'xl':   ['1.25rem',  { lineHeight: '1.75rem', letterSpacing: '-0.01em' }],
        '2xl':  ['1.5rem',   { lineHeight: '2rem',    letterSpacing: '-0.02em' }],
        '3xl':  ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.02em' }],
      },
      colors: {
        brand: {
          blue:  '#1E3A5F',
          gold:  '#F5A623',
          light: '#F0F4F8',
        },
      },
    },
  },
  safelist: [
    'lg:left-16',
    'lg:left-64',
  ],
  plugins: [],
}