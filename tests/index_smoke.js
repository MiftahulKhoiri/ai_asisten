// Tes asap layar "Mulai sesi" di web/index.js: pilih skill -> pilih model -> tekan Mulai (butuh node).
// Dipakai oleh tests/test_web.py.
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
assert.same = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);
const kode = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.js'), 'utf8');

function lingkungan(opsi) {
  const byId = {}, panggilan = [], lemari = Object.assign({aa_token: 'TOK'}, opsi.lemari || {});
  function mk(tag, id) {
    const e = {
      tag, id, children: [], dataset: {}, style: {}, className: '', _text: '', hidden: false, value: '', attrs: {},
      disabled: false, scrollHeight: 0, scrollTop: 0, clientHeight: 0, onclick: null, handlers: {}, parentElement: null, classes: new Set(),
      get textContent() { return this._text; }, set textContent(v) { this._text = String(v); this.children = []; },
      get innerHTML() { return ''; }, set innerHTML(v) { this.children = []; },
      appendChild(n) { if (n && typeof n === 'object') n.parentElement = this; this.children.push(n); return n; },
      append(...n) { n.forEach(x => this.appendChild(x)); }, remove() {}, focus() {}, select() {}, scrollTo() {},
      setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      addEventListener(t, f) { this.handlers[t] = f; }, closest() { return mk('x'); }, querySelector() { return mk('x'); },
      querySelectorAll() { return []; }, insertBefore(n) { return this.appendChild(n); },
    };
    e.classList = {toggle(c, on) { if (on === undefined ? !e.classes.has(c) : on) e.classes.add(c); else e.classes.delete(c); },
      add(c) { e.classes.add(c); }, remove(c) { e.classes.delete(c); }, contains(c) { return e.classes.has(c); }};
    return e;
  }
  const skillBtn = ['tanpa', 'web', 'dasar', 'kompleks', 'kritis'].map(s => { const b = mk('button'); b.dataset.skill = s; return b; });
  const document = {
    getElementById: id => byId[id] || (byId[id] = mk('div', id)), createElement: t => mk(t), createTextNode: t => Object.assign(mk('#text'), {_text: t}),
    querySelectorAll: sel => (sel === '#seg button' ? skillBtn : []), addEventListener() {}, body: mk('body'), documentElement: mk('html'), hidden: false,
  };
  const status = () => Object.assign({status: 'kosong', pesan: '', models: opsi.models, skills: {web: 4, dasar: 4, kompleks: 27},
    skill_tools: {}, skill_bawaan: 'kompleks', auto: false, agent: null}, opsi.status || {});
  const respon = (kode_, obj) => ({ok: kode_ < 400, status: kode_, json: async () => obj});
  async function fetchPalsu(url, o) {
    o = o || {}; panggilan.push({url, metode: o.method || 'GET', body: o.body});
    if (url === '/api/status') return respon(200, status());
    if (url === '/api/model/pilih') { opsi.status = {status: 'memuat', pesan: 'Memuat ' + JSON.parse(o.body).model + ' ...'}; return respon(200, {ok: true}); }   // seperti server asli
    if (url === '/api/chat') return respon(200, {chats: []});
    return respon(200, {});
  }
  const konteks = {
    window: {addEventListener() {}, visualViewport: null, matchMedia: () => ({matches: false, addEventListener() {}}), innerHeight: 800},
    document, console, fetch: fetchPalsu, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
    localStorage: {getItem: k => (k in lemari ? lemari[k] : null), setItem: (k, v) => { lemari[k] = String(v); }, removeItem: k => { delete lemari[k]; }},
    location: {search: '', pathname: '/', hash: ''}, history: {replaceState() {}}, URLSearchParams, navigator: {clipboard: null},
    requestAnimationFrame: f => f(), TextDecoder, TextEncoder, Intl, Date, JSON, Math, Promise, Set, Map,
  };
  konteks.window.localStorage = konteks.localStorage; konteks.window.document = document;
  vm.createContext(konteks); vm.runInContext(kode, konteks);
  return {byId, panggilan, lemari, skillBtn, ubahStatus: v => { opsi.status = v; }};
}
const tunggu = ms => new Promise(r => setTimeout(r, ms));
const MODEL = [{id: 'A', mb: 1000}, {id: 'B', mb: 2500}];
const kelas = e => ' ' + e.className + ' ';

(async () => {
  // --- 1. awal: tidak ada model terpilih, Mulai mati, tidak memuat apa pun
  let L = lingkungan({models: MODEL}); await tunggu(60);
  const daftar = L.byId['daftarModel'], mulai = L.byId['btnMulai'];
  assert.strictEqual(daftar.children.length, 2);
  assert.ok(daftar.children.every(b => !kelas(b).includes(' on ')));
  assert.strictEqual(mulai.disabled, true); assert.strictEqual(L.byId['mulaiKet'].textContent, 'Pilih satu model di atas dulu.');
  assert.strictEqual(daftar.children[1].attrs['role'], 'radio');

  // --- 2. mengetuk model HANYA menandai, belum memuat
  daftar.children[1].onclick();
  assert.ok(kelas(daftar.children[1]).includes(' on ') && !kelas(daftar.children[0]).includes(' on '));
  assert.strictEqual(daftar.children[1].attrs['aria-checked'], 'true'); assert.strictEqual(daftar.children[0].attrs['aria-checked'], 'false');
  assert.strictEqual(mulai.disabled, false);
  assert.ok(L.byId['mulaiKet'].textContent.startsWith('Siap: B · '), L.byId['mulaiKet'].textContent);
  assert.strictEqual(L.lemari['aa_model_pilih'], 'B');
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/model/pilih').length, 0, 'belum boleh memuat sebelum Mulai');
  daftar.children[0].onclick();                                   // ganti pilihan: tetap belum memuat
  assert.ok(kelas(daftar.children[0]).includes(' on ') && !kelas(daftar.children[1]).includes(' on '));
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/model/pilih').length, 0);

  // --- 3. skill diubah sebelum Mulai: ringkasan ikut berubah
  L.skillBtn[1].onclick();                                        // aktifkan Web (skill sudah 'kompleks' bawaan)
  assert.ok(L.byId['mulaiKet'].textContent.includes('Web'), L.byId['mulaiKet'].textContent);
  const skillTerpilih = ['kompleks', 'web'];

  // --- 4. Mulai: barulah model dimuat, dengan model dan skill yang dipilih
  mulai.onclick(); await tunggu(40);
  const pilih = L.panggilan.filter(p => p.url === '/api/model/pilih'); assert.strictEqual(pilih.length, 1);
  const b = JSON.parse(pilih[0].body); assert.strictEqual(b.model, 'A'); assert.same(b.skill.slice().sort(), skillTerpilih.slice().sort());
  assert.strictEqual(L.byId['modelPesan'].textContent, 'Memuat A ...');
  assert.strictEqual(mulai.disabled, true); assert.strictEqual(mulai.textContent, 'Memuat ...');

  // --- 5. dimuat ulang saat status 'memuat': Mulai tetap mati sampai selesai atau gagal
  L = lingkungan({models: MODEL, status: {status: 'memuat', pesan: 'Memuat B ...'}, lemari: {aa_model_pilih: 'B'}}); await tunggu(60);
  assert.strictEqual(L.byId['btnMulai'].disabled, true); assert.strictEqual(L.byId['btnMulai'].textContent, 'Memuat ...');
  L = lingkungan({models: MODEL, status: {status: 'error', pesan: 'kehabisan memori'}, lemari: {aa_model_pilih: 'B'}}); await tunggu(60);
  assert.strictEqual(L.byId['btnMulai'].disabled, false, 'setelah gagal bisa dicoba lagi'); assert.ok(L.byId['modelPesan'].textContent.includes('kehabisan memori'));

  // --- 6. pilihan diingat; model yang sudah hilang dari daftar dilupakan; satu-satunya model langsung ditandai
  L = lingkungan({models: MODEL, lemari: {aa_model_pilih: 'B'}}); await tunggu(60);
  assert.ok(kelas(L.byId['daftarModel'].children[1]).includes(' on ')); assert.strictEqual(L.byId['btnMulai'].disabled, false);
  L = lingkungan({models: MODEL, lemari: {aa_model_pilih: 'sudah-dihapus'}}); await tunggu(60);
  assert.ok(L.byId['daftarModel'].children.every(x => !kelas(x).includes(' on '))); assert.strictEqual(L.byId['btnMulai'].disabled, true);
  L = lingkungan({models: [{id: 'Tunggal', mb: 900}]}); await tunggu(60);
  assert.ok(kelas(L.byId['daftarModel'].children[0]).includes(' on ')); assert.strictEqual(L.byId['btnMulai'].disabled, false);
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/model/pilih').length, 0, 'pilihan otomatis tidak memuat');
  L = lingkungan({models: []}); await tunggu(60);
  assert.strictEqual(L.byId['btnMulai'].disabled, true);
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
