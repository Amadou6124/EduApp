/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './apps/**/*.py',
    './static/**/*.js',
  ],

  theme: {
    extend: {

      /* ───────────────────────────────────────────────
       * TYPOGRAPHIE — Manrope (chargée via Google Fonts)
       * ─────────────────────────────────────────────── */
      fontFamily: {
        sans: ['Manrope', 'system-ui', 'sans-serif'],
      },

      // Échelle alignée sur le design system :
      // H1 24/600 · H2 20/600 · H3 16/600 · Body 14/400 · Small 12/400 · Micro 11/500
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem',    letterSpacing: '0.01em' }], // 11px — labels/badges micro
        'xs':  ['0.75rem',   { lineHeight: '1rem',    letterSpacing: '0.01em' }], // 12px — small
        'sm':  ['0.875rem',  { lineHeight: '1.25rem', letterSpacing: '0.01em' }], // 14px — body
        'base':['1rem',      { lineHeight: '1.5rem',  letterSpacing: '0' }],      // 16px — H3
        'lg':  ['1.125rem',  { lineHeight: '1.75rem', letterSpacing: '-0.01em' }],
        'xl':  ['1.25rem',   { lineHeight: '1.75rem', letterSpacing: '-0.01em' }], // 20px — H2
        '2xl': ['1.5rem',    { lineHeight: '2rem',    letterSpacing: '-0.02em' }], // 24px — H1
        '3xl': ['1.875rem',  { lineHeight: '2.25rem', letterSpacing: '-0.02em' }], // 30px — KPI
      },

      /* ───────────────────────────────────────────────
       * COULEURS
       * ─────────────────────────────────────────────── */
      colors: {

        // ── Palette PRIMAIRE — Indigo ──
        // Portails Admin · Directeur · Prof · Parent · Promoteur · Superadmin
        primary: {
          50:  '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#6366F1', // accent / focus ring
          600: '#4F46E5', // ← boutons, état actif
          700: '#4338CA', // ← hover
          800: '#3730A3',
          900: '#312E81', // ← textes foncés
          950: '#1E1B4B',
        },

        // ── Palette ÉLÈVE — Emerald ──
        // Portail /learn/ exclusivement
        student: {
          50:  '#ECFDF5',
          100: '#D1FAE5',
          200: '#A7F3D0',
          300: '#6EE7B7',
          400: '#34D399',
          500: '#10B981', // ← principal
          600: '#059669', // ← hover
          700: '#047857',
          800: '#065F46',
          900: '#064E3B',
          950: '#022C22',
        },

        // ── Accent OR — XP, badges, niveaux (partagé) ──
        gold: {
          DEFAULT: '#F59E0B',
          50:  '#FFFBEB',
          100: '#FEF3C7',
          400: '#FBBF24',
          500: '#F59E0B', // accent principal
          600: '#D97706', // hover
        },

        // ── Couleurs sémantiques (status) ──
        success: '#10B981',
        warning: '#F59E0B',
        danger:  '#EF4444',
        info:    '#6366F1',

        // ── ALIAS TEMPORAIRES (fallback) ──
        // Conservés pour ne rien casser pendant la migration des templates.
        // À SUPPRIMER en Phase E une fois les 419 occurrences migrées.
        brand: {
          blue:  '#1E3A5F',
          gold:  '#F5A623',
          light: '#F0F4F8',
        },
      },

      /* ───────────────────────────────────────────────
       * OMBRES — design system (sm / md / lg)
       * ─────────────────────────────────────────────── */
      boxShadow: {
        'sm': '0 1px 3px rgba(0,0,0,0.08)',
        'md': '0 4px 16px rgba(0,0,0,0.10)',
        'lg': '0 8px 32px rgba(0,0,0,0.12)',
      },

      /* ───────────────────────────────────────────────
       * ANIMATIONS — keyframes toast (bottom-center)
       * (les autres keyframes restent dans input.css @layer utilities)
       * ─────────────────────────────────────────────── */
      keyframes: {
        toastIn: {
          '0%':   { opacity: '0', transform: 'translate(-50%, 16px)' },
          '100%': { opacity: '1', transform: 'translate(-50%, 0)' },
        },
        toastOut: {
          '0%':   { opacity: '1', transform: 'translate(-50%, 0)' },
          '100%': { opacity: '0', transform: 'translate(-50%, 16px)' },
        },
      },
      animation: {
        'toast-in':  'toastIn 0.2s ease-out forwards',
        'toast-out': 'toastOut 0.15s ease-in forwards',
      },
    },
  },

  /* ───────────────────────────────────────────────
   * NOTES design system (défauts Tailwind = conformes, non surchargés) :
   *  • Border-radius : rounded-lg=8px (inputs/btn) · rounded-xl=12px (cards)
   *                    rounded-2xl=16px (modals) · rounded-full (pills)
   *  • Spacing 4px-grid : 1=4 · 2=8 · 3=12 · 4=16 · 6=24 · 8=32 · 12=48
   * ─────────────────────────────────────────────── */

  // Classes générées dynamiquement (offset sidebar) → jamais purgées
  safelist: [
    'lg:left-16',
    'lg:left-64',
  ],

  plugins: [],
}
