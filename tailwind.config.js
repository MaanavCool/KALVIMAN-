export default {
  content: ["./index.html","./src/**/*.{js,jsx}"],
  darkMode: 'class',
  theme: { extend: {
    colors: {
      sky: { 500:'#0ea5e9',600:'#0284c7',400:'#38bdf8',300:'#7dd3fc' },
      rose: { 500:'#e11d48',400:'#fb7185',600:'#be123c' },
      mint: { 500:'#22c55e',400:'#4ade80' },
      navy: { DEFAULT:'#0c1222',700:'#1a2744',800:'#0f172a',900:'#020617' },
    },
    fontFamily: { display:['Barlow Condensed','sans-serif'], body:['Plus Jakarta Sans','Inter','sans-serif'] },
  }},
}
