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
      querySelectorAll(sel) { return sel[0] === '.' ? this.children.filter(c => ' ' + c.className + ' ').filter(c => (' ' + c.className + ' ').includes(' ' + sel.slice(1) + ' ')) : []; }, insertBefore(n) { return this.appendChild(n); },
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

  // --- 1b. daftar model tersembunyi di balik tombol; terbuka hanya saat diketuk
  const tombolModel = L.byId['btnDaftarModel'], panel = L.byId['modelPanel'];
  assert.strictEqual(panel.hidden, true, 'daftar tertutup di awal');
  assert.strictEqual(tombolModel.disabled, false);
  assert.strictEqual(L.byId['modelLabel'].textContent, 'Pilih model');
  assert.strictEqual(L.byId['modelJumlah'].textContent, '2 model tersedia');
  assert.strictEqual(tombolModel.attrs['aria-expanded'], 'false');
  tombolModel.onclick();
  assert.strictEqual(panel.hidden, false); assert.strictEqual(tombolModel.attrs['aria-expanded'], 'true');
  tombolModel.onclick();                                           // ketuk lagi: menutup
  assert.strictEqual(panel.hidden, true);
  tombolModel.onclick();                                           // buka lagi untuk memilih

  // --- 2. mengetuk model HANYA menandai, belum memuat
  daftar.children[1].onclick();
  assert.strictEqual(panel.hidden, true, 'setelah memilih, daftar menutup');
  assert.strictEqual(L.byId['modelLabel'].textContent, 'B', 'tombol menampilkan model terpilih');
  assert.ok(L.byId['modelJumlah'].textContent.includes('2 model tersedia'));
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
  tombolModel.onclick(); assert.strictEqual(panel.hidden, false);   // daftar terbuka lalu Mulai ditekan
  mulai.onclick(); await tunggu(40);
  assert.strictEqual(panel.hidden, true, 'saat memuat, daftar menutup'); assert.strictEqual(tombolModel.disabled, true);
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
  assert.strictEqual(L.byId['modelLabel'].textContent, 'Tunggal', 'satu-satunya model langsung tampil di tombol');
  L = lingkungan({models: []}); await tunggu(60);
  assert.strictEqual(L.byId['btnMulai'].disabled, true);
  assert.strictEqual(L.byId['btnDaftarModel'].disabled, true); assert.strictEqual(L.byId['modelLabel'].textContent, 'Tidak ada model');
  L.byId['btnDaftarModel'].onclick(); assert.strictEqual(L.byId['modelPanel'].hidden, true, 'tanpa model, daftar tidak bisa dibuka');

  // --- 12. beberapa sumber: daftar dikelompokkan Lokal / Online, tiap model berlencana, nama tampil tanpa kunci "cid::"
  const KON = {daftar: [
    {id: 'lokal', nama: 'llama-server', jenis: 'llama', alamat: 'http://127.0.0.1:8080', key_ada: false, utama: true, ok: true, jumlah: 2, galat: ''},
    {id: 'kor1', nama: 'OpenRouter', jenis: 'online', alamat: 'https://openrouter.ai/api/v1', key_ada: true, utama: false, ok: true, jumlah: 2, galat: ''},
    {id: 'kmati', nama: 'Mati', jenis: 'online', alamat: 'https://mati.example/v1', key_ada: true, utama: false, ok: false, jumlah: 0, galat: 'Ditolak server (401)'}]};
  const CAMPUR = [
    {id: 'A', nama: 'A', mb: 1000, koneksi: 'lokal', jenis: 'lokal', sumber: 'llama-server', router: true},
    {id: 'B', nama: 'B', mb: 2500, koneksi: 'lokal', jenis: 'lokal', sumber: 'llama-server', router: true},
    {id: 'kor1::gpt-4o', nama: 'gpt-4o', koneksi: 'kor1', jenis: 'online', sumber: 'OpenRouter', router: false},
    {id: 'kor1::llama-3', nama: 'llama-3', koneksi: 'kor1', jenis: 'online', sumber: 'OpenRouter', router: false}];
  L = lingkungan({models: CAMPUR, status: {koneksi: KON, model_tampil: 'gpt-4o'}}); await tunggu(60);
  let ch = L.byId['daftarModel'].children;
  assert.deepStrictEqual(ch.map(x => x.dataset.model || ('#' + x.dataset.grup)), ['#lokal', 'A', 'B', '#kor1', 'kor1::gpt-4o', 'kor1::llama-3']);
  assert.strictEqual(ch[0]._text, 'Lokal · llama-server'); assert.strictEqual(ch[3]._text, 'Online · OpenRouter');
  assert.ok(kelas(ch[3]).includes(' online '));
  assert.strictEqual(L.byId['modelJumlah'].textContent, '4 model tersedia');
  assert.strictEqual(L.byId['koneksiGalat'].hidden, false);
  assert.strictEqual(L.byId['koneksiGalat'].textContent, 'Mati: Ditolak server (401)');
  // memilih model online: tombol memakai nama polos + lencana Online; kunci "kor1::" tak tampil; yang dikirim ke server tetap kunci lengkap
  L.byId['btnDaftarModel'].onclick(); ch[4].onclick();
  assert.strictEqual(L.byId['modelLabel'].textContent, 'gpt-4o');
  assert.strictEqual(L.byId['modelBadge'].hidden, false); assert.strictEqual(L.byId['modelBadge'].textContent, 'Online');
  assert.ok(kelas(L.byId['modelBadge']).includes(' online '));
  assert.ok(/^Siap: gpt-4o/.test(L.byId['mulaiKet'].textContent), L.byId['mulaiKet'].textContent);
  L.byId['btnMulai'].onclick(); await tunggu(20);
  assert.strictEqual(JSON.parse(L.panggilan.find(p => p.url === '/api/model/pilih').body).model, 'kor1::gpt-4o');
  // model lokal: lencana Lokal
  L = lingkungan({models: CAMPUR, status: {koneksi: KON}, lemari: {aa_model_pilih: 'B'}}); await tunggu(60);
  assert.strictEqual(L.byId['modelBadge'].textContent, 'Lokal');
  // pencarian: judul kelompok yang semua modelnya tersaring ikut sembunyi
  L.byId['cariModel'].value = 'gpt'; L.byId['cariModel'].oninput();
  ch = L.byId['daftarModel'].children;
  assert.deepStrictEqual(ch.map(x => x.hidden), [true, true, true, false, false, true]);
  L.byId['cariModel'].value = 'llama'; L.byId['cariModel'].oninput();          // cocok di nama model online saja
  assert.deepStrictEqual(ch.map(x => x.hidden), [true, true, true, false, true, false]);
  L.byId['cariModel'].value = ''; L.byId['cariModel'].oninput();
  assert.ok(ch.every(x => !x.hidden));
  // nama bawaan koneksi utama ("Lokal") tidak diulang di judul
  L = lingkungan({models: CAMPUR.map(m => m.koneksi === 'lokal' ? Object.assign({}, m, {sumber: 'Lokal'}) : m), status: {koneksi: KON}}); await tunggu(60);
  assert.strictEqual(L.byId['daftarModel'].children[0]._text, 'Lokal');
  // satu sumber saja: tanpa judul kelompok, galat koneksi tersembunyi
  L = lingkungan({models: MODEL, status: {koneksi: {daftar: [KON.daftar[0]]}}}); await tunggu(60);
  assert.ok(L.byId['daftarModel'].children.every(x => x.dataset.model !== undefined));
  assert.strictEqual(L.byId['koneksiGalat'].hidden, true);
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
