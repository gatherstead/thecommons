/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        primary: '#355E4C', // Earthy Pine
        accent: '#CD6954',  // Terracotta Coral (CTA)
        accent2: '#7F9E5D', // Leaf Green
        background: '#F9F7F2', // Weathered Cream
        text: '#2B2B2B', // Soft Charcoal
        subtle: '#A7A7A2', // Cool Dust
      },
      fontFamily: {
        display: ['Fraunces', 'serif'],
        heading: ['Public Sans', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
        alt: ['IBM Plex Sans', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
