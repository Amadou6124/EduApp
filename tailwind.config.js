/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './apps/**/*.py',
    './static/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          blue:  '#1E3A5F',
          gold:  '#F5A623',
          light: '#F0F4F8',
        },
      },
    },
  },
  plugins: [],
}