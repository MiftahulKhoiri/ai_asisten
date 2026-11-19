/* teks.js - pengubah teks bersama untuk Sesi AI Asisten (index.js) dan Sesi Agent (agent.js).
   esc(): hindari HTML; md(): markdown kecil yang AMAN (semua teks di-escape dulu, hanya
   blok kode ```, `kode`, **tebal**, dan baris baru yang dijadikan HTML). Dimuat SEBELUM index.js/agent.js. */
(function () {
  'use strict';
  function esc(s) {
    return s.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  }
  function md(s) {
    return s.split('```').map((p, i) => {
      if (i % 2 === 1) {
        const nl = p.indexOf('\n');
        const kode = (nl >= 0 && /^[\w+-]*$/.test(p.slice(0, nl).trim())) ? p.slice(nl + 1) : p;
        return '<div class="kode"><button type="button" class="salin">Salin</button><pre><code>' +
          esc(kode.replace(/\n$/, '')) + '</code></pre></div>';
      }
      return esc(p)
        .replace(/`([^`\n]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    }).join('');
  }
  globalThis.AsistenTeks = {esc, md};
})();
