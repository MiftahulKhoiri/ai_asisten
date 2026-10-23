// Tes asap web/agent.js: memutar event NDJSON asli dari orkestrator ke halaman dengan DOM tiruan.
// Dipakai oleh tests/test_tim.py (dilewati bila node tidak terpasang).
// Pemakaian: node tests/agent_smoke.js <berkas-ndjson> [mode]
//   mode kosong      kirim perintah, proses dipantau lewat long-poll
//   mode putus       sama, tetapi jaringan putus dua kali di tengah pemantauan (harus lanjut sendiri)
//   mode lampirkan   halaman dibuka saat proses sudah berjalan di server (tanpa mengirim apa pun)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ndjson = fs.readFileSync(process.argv[2], 'utf8');
const MODE = process.argv[3] || '';
// server menambahkan 'ts' (detik sejak proses mulai) ke tiap event: dipakai untuk waktu di log
const EVENTS = ndjson.split('\n').filter(b => b.trim()).map((b, i) => Object.assign(JSON.parse(b), {ts: i * 2}));
const kode = fs.readFileSync(path.join(__dirname, '..', 'web', 'agent.js'), 'utf8');

const semua = [];          // semua elemen yang dibuat
const byId = {};
function mk(tag, id) {
  const e = {
    tag, id, children: [], dataset: {}, style: {}, className: '', _text: '', innerHTML: '', hidden: false,
    value: '', handlers: {}, attrs: {}, open: false, disabled: false, scrollHeight: 100, scrollTop: 0, clientHeight: 100,
    onclick: null, onchange: null, parentElement: null,
    classes: new Set(),
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children = []; },
    classList: null,
    append(...n) { for (const x of n) this.appendChild(x); },
    appendChild(n) { if (n && typeof n === 'object') n.parentElement = this; this.children.push(n); return n; },
    remove() {}, focus() {}, select() {}, setSelectionRange() {},
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    addEventListener(t, f) { this.handlers[t] = f; },
    querySelector() { return mk('x'); }, querySelectorAll() { return []; }, closest() { return null; },
  };
  e.classList = {
    toggle(c, on) { if (on === undefined ? !e.classes.has(c) : on) e.classes.add(c); else e.classes.delete(c); },
    add(c) { e.classes.add(c); }, remove(c) { e.classes.delete(c); }, contains(c) { return e.classes.has(c); },
  };
  semua.push(e);
  return e;
}
function teksPohon(e) {
  if (typeof e === 'string') return e;
  return (e._text || '') + (e.children || []).map(teksPohon).join(' ');
}

const document = {
  getElementById(id) {   // elemen yang dibuat lewat createElement dan sudah dipasang dicari lebih dulu
    const dibuat = semua.filter(e => e.id === id && e.parentElement).pop();
    return dibuat || byId[id] || (byId[id] = mk('div', id));
  },
  createElement(tag) { return mk(tag); },
  createTextNode(t) { const n = mk('#text'); n._text = t; return n; },
  querySelectorAll() { return []; },
  addEventListener(t, f) { (this._h = this._h || {})[t] = f; },
  body: mk('body'), hidden: false, execCommand() { return true; },
};
const kirimBody = { teks: null };
const panggilan = [];      // semua fetch DELETE/POST penghapusan riwayat
function respon(obj, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => obj };
}
const poll = {dari: [], gagal: 0};     // nomor 'dari' tiap long-poll, dan berapa kali jaringan sengaja diputus
function potong(dari, jumlah) {
  const akhir = Math.min(EVENTS.length, dari + jumlah);
  return {sesi: 's1', aktif: akhir < EVENTS.length, habis: akhir >= EVENTS.length, dari, next: akhir,
          lalu: 42, events: EVENTS.slice(dari, akhir)};
}
async function fetchPalsu(url, opt) {
  if (url === '/api/agent/status') {
    const proses = MODE === 'lampirkan'
      ? {sesi: 's1', id: null, tugas: 'buat program halo', aktif: true, status: null, lalu: 42} : null;
    return respon({models: [{id: 'A', mb: 1100}, {id: 'B', mb: 2300}], chat_aktif: false,
                   sibuk: false, proses});
  }
  if (url.startsWith('/api/agent/event?')) {
    const q = new URLSearchParams(url.split('?')[1]);
    poll.dari.push(Number(q.get('dari')));
    if (MODE === 'putus' && poll.dari.length > 1 && poll.gagal < 2 && poll.dari.length % 2 === 0) {
      poll.gagal++;
      throw new TypeError('Failed to fetch');
    }
    return respon(potong(Number(q.get('dari')), MODE === 'lampirkan' ? 5000 : 7));   // beberapa event per jawaban
  }
  if (url === '/api/agent/riwayat') {
    return respon({run: [
      {id: '20261018-100000-aaaa', judul: 'Satu', status: 'lolos', dibuat: '2026-10-18T10:00:00', putaran: 1, maks: 3},
      {id: '20261018-110000-bbbb', judul: 'Dua', status: 'belum', dibuat: '2026-10-18T11:00:00', putaran: 3, maks: 3},
    ]});
  }
  if (opt && (opt.method === 'DELETE' || url === '/api/agent/riwayat/hapus-semua')) {
    panggilan.push((opt.method || 'GET') + ' ' + url);
    return respon({ok: true, dihapus: 2});
  }
  if (url === '/api/agent/jalankan') {
    kirimBody.teks = JSON.parse(opt.body);
    return respon({ok: true, sesi: 's1'});
  }
  return respon({});
}
const galat = [];
const konteks = {
  document, window: {isSecureContext: false}, navigator: {}, fetch: fetchPalsu,
  localStorage: {getItem: k => (k === 'aa_token' ? 'tok' : null), setItem() {}},
  location: {search: '', pathname: '/agent.html'}, history: {replaceState() {}},
  URLSearchParams, TextDecoder, TextEncoder, console, confirm: () => true,
  setInterval: () => 0, clearInterval() {}, setTimeout, clearTimeout,
};
konteks.window.document = document;
konteks.window.AGENT_JEDA_ULANG = 5;   // jeda coba-lagi dipercepat untuk tes
vm.createContext(konteks);

(async () => {
  try {
    vm.runInContext(kode, konteks, {filename: 'agent.js'});
    await new Promise(r => setTimeout(r, 60));
    if (MODE !== 'lampirkan') {
      byId['input'].value = 'buat program halo';
      await byId['bawah'].handlers.submit({preventDefault() {}});
    }
    for (let i = 0; i < 100 && !byId['lencanaLog'].classes.has('selesai') && !byId['lencanaLog'].classes.has('gagal'); i++) {
      await new Promise(r => setTimeout(r, 20));
    }
    await new Promise(r => setTimeout(r, 30));
  } catch (e) {
    galat.push(String(e && e.stack || e));
  }
  // keadaan tombol saran dicatat sebelum langkah hapus riwayat di bawah (yang menyembunyikannya)
  const saranTampil = !!byId['saranBar'] && byId['saranBar'].hidden === false;
  const saranTeks = byId['saranTeks'] && byId['saranTeks']._text;
  const lencana = byId['lencanaLog'];
  // buka panel log setelah proses selesai (baris log digambar saat panel dibuka)
  try { lencana.onclick(); } catch (e) { galat.push(String(e && e.stack || e)); }
  const baris = semua.filter(e => /\blg\b/.test(e.className));
  const err = semua.filter(e => /\binfo err\b/.test(e.className)).map(teksPohon);
  const model = (byId['logModel'].children || []).map(teksPohon);
  try { byId['btnTutupLog'].onclick(); } catch (e) { galat.push(String(e && e.stack || e)); }
  // hapus riwayat: tombol per item dan 'Hapus semua'
  try {
    const tombolX = semua.filter(e => e.className === 'x');
    await tombolX[tombolX.length - 1].onclick();
    await byId['btnHapusRiwayat'].onclick();
    await new Promise(r => setTimeout(r, 30));
  } catch (e) { galat.push(String(e && e.stack || e)); }
  const hasil = {
    galat, err, dikirim: kirimBody.teks && kirimBody.teks.teks,
    baris_log: baris.length,
    lencana_tampil: lencana.hidden === false,
    lencana_selesai: lencana.classes.has('selesai'),
    kata: byId['lencanaKata']._text,
    teks_log: baris.map(teksPohon),
    model, hapus: panggilan, tombol_x: semua.filter(e => e.className === 'x').length,
    kartu: semua.filter(e => /\btahap\b/.test(e.className)).length,
    poll_dari: poll.dari, putus: poll.gagal, sibuk_akhir: byId['btnKirim'].className,
    info: semua.filter(e => /\binfo\b/.test(e.className)).map(teksPohon),
    alur: (byId['relAlur'] ? byId['relAlur'].children : []).map(c => ({id: c.id, kelas: c.className, nama: c.children[1] && c.children[1]._text, bl: c.children[0] && c.children[0]._text})),
    alur_kolom: byId['relAlur'] && byId['relAlur'].style.gridTemplateColumns,
    saran_tampil: saranTampil, saran_teks: saranTeks,
    kartu_diag: semua.filter(e => /\bdiag\b/.test(e.className)).length,
    jalur_cek: ['otomatis', 'buat', 'perbaiki', 'cari_bug'].map(j => byId['jl_' + j] && byId['jl_' + j].attrs['aria-checked']),
  };
  console.log(JSON.stringify(hasil));
  process.exit(galat.length || err.length ? 1 : 0);
})();
