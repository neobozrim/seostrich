/** @type {import('tailwindcss').Config}
 *
 * SEOstrich brand palette — derived from design-assets/web/tokens.css:
 * brown #6B4226 (brand), sand #F1E4D4, ink #191411, ink-muted #5F5449,
 * paper #FFFFFF, line #E6E1D8, brown-hover #56351E, brown-tint #F5EDE6.
 */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#FAF6F2',
          100: '#F5EDE6',
          200: '#E6D3C3',
          300: '#C9A487',
          400: '#6B4226',
          500: '#56351E',
          600: '#4A2E1A',
          700: '#3E2615',
          800: '#322011',
          900: '#27190D',
        },
        accent: {
          50: '#F5EDE6',
          100: '#EBDDD0',
          200: '#DCC6B0',
          300: '#C9A487',
          400: '#A87350',
          500: '#8C5A38',
          600: '#6B4226',
          700: '#56351E',
          800: '#4A2E1A',
          900: '#3E2615',
        },
        secondary: {
          50: '#F7F4EF',
          100: '#EFEAE2',
          200: '#E0D8CC',
          300: '#CFC4B4',
          400: '#B3A591',
          500: '#948672',
          600: '#7A6F5F',
          700: '#5F5449',
          800: '#40382F',
          900: '#191411',
        },
        // The single action colour. Everything else on the page is brown, sand
        // and cream; the one thing you DO — start — is the only blue.
        action: {
          50: '#EAF1FD',
          100: '#D6E3FB',
          300: '#8FB1F2',
          400: '#2E6BE6',
          500: '#245BC9',
          600: '#1D4BA8',
        },
        surface: {
          50: '#FCFAF8',
          100: '#F9F5F0',
          200: '#F1E4D4',
          300: '#E6E1D8',
          400: '#D8CFC0',
          500: '#BFB3A0',
          600: '#9C8F7C',
          700: '#7A6F5F',
          800: '#5F5449',
          900: '#191411',
        },
      },
      fontFamily: {
        sans: ['var(--font-body)', 'system-ui', '-apple-system', 'Segoe UI', 'Arial', 'sans-serif'],
        display: ['var(--font-display)', 'Avenir Next', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
