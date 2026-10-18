// Tes asap web/agent.js: memutar event NDJSON asli dari orkestrator ke halaman dengan DOM tiruan.
// Dipakai oleh tests/test_web.py (dilewati bila node tidak terpasang).
// Pemakaian: node tests/agent_smoke.js <berkas-ndjson>
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ndjson = fs.readFileSync(process.argv[2], 'utf8');
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
  getElementById(id) { return byId[id] || (byId[id] = mk('div', id)); },
  createElement(tag) { return mk(tag); },
  createTextNode(t) { const n = mk('#text'); n._text = t; return n; },
  querySelectorAll() { return []; },
  addEventListener(t, f) { (this._h = this._h || {})[t] = f; },
  body: mk('body'), hidden: false, execCommand() { return true; },
};
const kirimBody = { teks: null };
function respon(obj, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => obj };
}
async function fetchPalsu(url, opt) {
  if (url === '/api/agent/status') {
    return respon({models: [{id: 'A', mb: 1100}, {id: 'B', mb: 2300}], chat_aktif: false, sibuk: false});
  }
  if (url === '/api/agent/riwayat') return respon({run: []});
  if (url === '/api/agent/jalankan') {
    kirimBody.teks = JSON.parse(opt.body);
    const enc = new TextEncoder().encode(ndjson);
    let sudah = false;
    return {ok: true, status: 200, body: {getReader() {
      return {read: async () => { if (sudah) return {done: true}; sudah = true; return {value: enc, done: false}; }};
    }}};
  }
  return respon({});
}
const galat = [];
const konteks = {
  document, window: {isSecureContext: false}, navigator: {}, fetch: fetchPalsu,
  localStorage: {getItem: k => (k === 'aa_token' ? 'tok' : null), setItem() {}},
  location: {search: '', pathname: '/agent.html'}, history: {replaceState() {}},
  URLSearchParams, TextDecoder, TextEncoder, console,
  setInterval: () => 0, clearInterval() {}, setTimeout, clearTimeout,
};
konteks.window.document = document;
vm.createContext(konteks);

(async () => {
  try {
    vm.runInContext(kode, konteks, {filename: 'agent.js'});
    await new Promise(r => setTimeout(r, 30));
    byId['input'].value = 'buat program halo';
    await byId['bawah'].handlers.submit({preventDefault() {}});
    await new Promise(r => setTimeout(r, 30));
  } catch (e) {
    galat.push(String(e && e.stack || e));
  }
  const lencana = byId['lencanaLog'];
  // buka panel log setelah proses selesai (baris log digambar saat panel dibuka)
  try { lencana.onclick(); } catch (e) { galat.push(String(e && e.stack || e)); }
  const baris = semua.filter(e => /\blg\b/.test(e.className));
  const err = semua.filter(e => /\binfo err\b/.test(e.className)).map(teksPohon);
  const model = (byId['logModel'].children || []).map(teksPohon);
  try { byId['btnTutupLog'].onclick(); } catch (e) { galat.push(String(e && e.stack || e)); }
  const hasil = {
    galat, err, dikirim: kirimBody.teks && kirimBody.teks.teks,
    baris_log: baris.length,
    lencana_tampil: lencana.hidden === false,
    lencana_selesai: lencana.classes.has('selesai'),
    kata: byId['lencanaKata']._text,
    teks_log: baris.map(teksPohon),
    model,
    kartu: semua.filter(e => /\btahap\b/.test(e.className)).length,
  };
  console.log(JSON.stringify(hasil));
  process.exit(galat.length || err.length ? 1 : 0);
})();
