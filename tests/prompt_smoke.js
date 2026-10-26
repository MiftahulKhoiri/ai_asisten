// Tes asap panel prompt untuk skill Tanpa (web/prompt.js + index.js) dengan DOM dan fetch tiruan (butuh node).
// Dipakai oleh tests/test_prompt.py.
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
assert.same = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);
const web = f => fs.readFileSync(path.join(__dirname, '..', 'web', f), 'utf8');

function lingkungan(opsi) {
  const byId = {}, panggilan = [], lemari = Object.assign({aa_token: 'TOK'}, opsi.lemari || {});
  const prompt = (opsi.prompt || [{id: 'bawaan', nama: 'Bawaan (asisten ramah)', isi: 'Kamu asisten. {waktu}', bawaan: true}]).map(p => Object.assign({}, p));
  function mk(tag, id) {
    const e = {
      tag, id, children: [], dataset: {}, style: {}, className: '', _text: '', hidden: false, value: '', attrs: {}, title: '', type: '',
      checked: false, disabled: false, onclick: null, onchange: null, handlers: {}, parentElement: null, classes: new Set(),
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
  // keadaan awal seperti di index.html (atribut hidden)
  for (const id of ['promptBox', 'promptRingkas', 'promptForm']) { byId[id] = mk('div', id); byId[id].hidden = true; }
  byId['langkahModel'] = mk('div', 'langkahModel');
  const skillBtn = ['tanpa', 'web', 'dasar', 'kompleks', 'kritis'].map(s => { const b = mk('button'); b.dataset.skill = s; return b; });
  const document = {
    getElementById: id => byId[id] || (byId[id] = mk('div', id)), createElement: t => mk(t), createTextNode: t => Object.assign(mk('#text'), {_text: t}),
    querySelectorAll: sel => (sel === '#seg button' ? skillBtn : []), addEventListener() {}, body: mk('body'), documentElement: mk('html'), hidden: false,
  };
  const status = () => Object.assign({status: 'kosong', pesan: '', models: [{id: 'A', mb: 1000}, {id: 'B', mb: 2500}], skills: {web: 4, dasar: 4, kompleks: 27},
    skill_tools: {}, skill_bawaan: 'kompleks', auto: false, agent: null}, opsi.status || {});
  const respon = (k, obj) => ({ok: k < 400, status: k, json: async () => obj});
  let nomor = 1;
  async function fetchPalsu(url, o) {
    o = o || {}; panggilan.push({url, metode: o.method || 'GET', body: o.body});
    if (url === '/api/status') return respon(200, status());
    if (url === '/api/model/pilih') { opsi.status = {status: 'memuat', pesan: 'Memuat ...'}; return respon(200, {ok: true}); }
    if (url === '/api/prompt' && !o.method) return opsi.galatDaftar ? respon(500, {error: 'server rusak'}) : respon(200, {prompt, bawaan: 'bawaan'});
    if (url === '/api/prompt' && o.method === 'POST') {
      const b = JSON.parse(o.body);
      if (prompt.some(p => p.nama.toLowerCase() === b.nama.toLowerCase())) return respon(400, {error: 'Sudah ada prompt dengan nama itu'});
      const baru = {id: 'p0000000' + (nomor++), nama: b.nama, isi: b.isi, bawaan: false}; prompt.push(baru);
      return respon(200, {ok: true, baru, prompt});
    }
    if (url === '/api/prompt/hapus') { const i = prompt.findIndex(p => p.id === JSON.parse(o.body).id); if (i > 0) prompt.splice(i, 1); return respon(200, {ok: true, prompt}); }
    if (url === '/api/chat') return respon(200, {chats: []});
    return respon(200, {});
  }
  let konfirmasi = true;
  const konteks = {
    window: {addEventListener() {}, visualViewport: null, matchMedia: () => ({matches: false, addEventListener() {}}), innerHeight: 800,
      confirm: () => konfirmasi},
    document, console, fetch: fetchPalsu, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
    localStorage: {getItem: k => (k in lemari ? lemari[k] : null), setItem: (k, v) => { lemari[k] = String(v); }, removeItem: k => { delete lemari[k]; }},
    location: {search: '', pathname: '/', hash: ''}, history: {replaceState() {}}, URLSearchParams, navigator: {clipboard: null},
    requestAnimationFrame: f => f(), TextDecoder, TextEncoder, Intl, Date, JSON, Math, Promise, Set, Map,
  };
  konteks.window.localStorage = konteks.localStorage; konteks.window.document = document;
  vm.createContext(konteks);
  vm.runInContext(web('prompt.js'), konteks); vm.runInContext(web('index.js'), konteks);
  return {byId, panggilan, lemari, skillBtn, prompt, setKonfirmasi: v => { konfirmasi = v; }};
}
const tunggu = ms => new Promise(r => setTimeout(r, ms));
const baris = L => L.byId['promptList'].children;                       // tiap baris: [label(cek, nama), tombol hapus?]
const cek = b => b.children[0].children[0];
const namaBaris = b => b.children[0].children[1].textContent;
const hapusBtn = b => b.children[1];
const kelas = e => ' ' + e.className + ' ';

(async () => {
  // --- 1. skill bawaan (kompleks): panel prompt tidak tampil dan daftar tidak diminta
  let L = lingkungan({}); await tunggu(60);
  assert.strictEqual(L.byId['promptBox'].hidden, true); assert.strictEqual(L.byId['langkahModel'].hidden, false);
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/prompt').length, 0);

  // --- 2. pilih skill Tanpa (bukan kompleks): panel tampil, langkah model menunggu "Selesai"
  L.skillBtn[0].onclick(); L.skillBtn[3].onclick(); await tunggu(60);          // aktifkan Tanpa, matikan Kompleks
  assert.strictEqual(L.byId['promptBox'].hidden, false, 'panel prompt tampil untuk skill Tanpa');
  assert.strictEqual(L.byId['langkahModel'].hidden, true, 'pilih model menunggu Selesai');
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/prompt').length, 1);
  assert.strictEqual(baris(L).length, 1); assert.strictEqual(namaBaris(baris(L)[0]), 'Bawaan (asisten ramah) · bawaan');
  assert.strictEqual(cek(baris(L)[0]).checked, true, 'Bawaan dicentang secara bawaan');
  assert.strictEqual(hapusBtn(baris(L)[0]), undefined, 'bawaan tidak punya tombol hapus');
  assert.ok(L.byId['promptKet'].textContent.startsWith('Dipilih: 1 prompt · ±'), L.byId['promptKet'].textContent);

  // --- 3. + prompt: validasi kolom, simpan, langsung dicentang
  const form = L.byId['promptForm']; assert.strictEqual(form.hidden, true);
  L.byId['btnPromptBaru'].onclick(); assert.strictEqual(form.hidden, false);
  L.byId['btnPromptSimpan'].onclick(); await tunggu(20);
  assert.strictEqual(L.byId['promptGalat'].textContent, 'Nama prompt wajib diisi.');
  L.byId['promptNama'].value = 'Penerjemah'; L.byId['btnPromptSimpan'].onclick(); await tunggu(20);
  assert.strictEqual(L.byId['promptGalat'].textContent, 'Isi prompt wajib diisi.');
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/prompt' && p.metode === 'POST').length, 0, 'tidak ada yang dikirim sebelum lengkap');
  L.byId['promptIsi'].value = 'Terjemahkan ke Inggris.'; L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.same(JSON.parse(L.panggilan.find(p => p.url === '/api/prompt' && p.metode === 'POST').body), {nama: 'Penerjemah', isi: 'Terjemahkan ke Inggris.'});
  assert.strictEqual(baris(L).length, 2); assert.strictEqual(namaBaris(baris(L)[1]), 'Penerjemah');
  assert.strictEqual(cek(baris(L)[1]).checked, true, 'prompt baru langsung dicentang');
  assert.strictEqual(form.hidden, true); assert.strictEqual(L.byId['promptNama'].value, ''); assert.strictEqual(L.byId['promptIsi'].value, '');
  assert.strictEqual(hapusBtn(baris(L)[1]).textContent, '(−)');
  assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), ['bawaan', 'p00000001']);
  assert.ok(L.byId['promptKet'].textContent.startsWith('Dipilih: 2 prompt'));
  // nama kembar ditolak server: pesan tampil di kolom dan form tetap terbuka
  L.byId['btnPromptBaru'].onclick(); L.byId['promptNama'].value = 'penerjemah'; L.byId['promptIsi'].value = 'x';
  L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.strictEqual(L.byId['promptGalat'].textContent, 'Sudah ada prompt dengan nama itu'); assert.strictEqual(form.hidden, false);
  L.byId['btnPromptBaru'].onclick();                                           // tutup form lagi

  // --- 4. centang beberapa prompt; tanpa satu pun = murni
  cek(baris(L)[0]).checked = false; cek(baris(L)[0]).onchange();
  assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), ['p00000001']);
  cek(baris(L)[1]).checked = false; cek(baris(L)[1]).onchange();
  assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), []);
  assert.ok(L.byId['promptKet'].textContent.includes('tanpa prompt sistem (murni)'), L.byId['promptKet'].textContent);
  cek(baris(L)[0]).checked = true; cek(baris(L)[0]).onchange(); cek(baris(L)[1]).checked = true; cek(baris(L)[1]).onchange();

  // --- 5. hapus dengan (−): konfirmasi dulu; batal tidak menghapus
  L.setKonfirmasi(false); hapusBtn(baris(L)[1]).onclick(); await tunggu(20);
  assert.strictEqual(baris(L).length, 2, 'batal konfirmasi: tidak terhapus');
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/prompt/hapus').length, 0);
  L.setKonfirmasi(true); hapusBtn(baris(L)[1]).onclick(); await tunggu(40);
  assert.same(JSON.parse(L.panggilan.find(p => p.url === '/api/prompt/hapus').body), {id: 'p00000001'});
  assert.strictEqual(baris(L).length, 1); assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), ['bawaan'], 'terhapus dari pilihan');
  // buat lagi satu untuk langkah berikut
  L.byId['btnPromptBaru'].onclick(); L.byId['promptNama'].value = 'Singkat'; L.byId['promptIsi'].value = 'Jawab satu kalimat.';
  L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), ['bawaan', 'p00000002']);

  // --- 6. Selesai: panel ditutup jadi ringkasan, pilih model & Mulai muncul
  L.byId['btnPromptSelesai'].onclick();
  assert.strictEqual(L.byId['promptBox'].hidden, true); assert.strictEqual(L.byId['promptRingkas'].hidden, false);
  assert.strictEqual(L.byId['promptRingkasTeks'].textContent, 'Prompt: Bawaan (asisten ramah), Singkat');
  assert.strictEqual(L.byId['langkahModel'].hidden, false); assert.strictEqual(L.lemari['aa_prompt_selesai'], '1');
  L.byId['daftarModel'].children[1].onclick();
  assert.ok(L.byId['mulaiKet'].textContent.includes('prompt: Bawaan (asisten ramah), Singkat'), L.byId['mulaiKet'].textContent);

  // --- 7. Mulai: id prompt ikut dikirim ke server bersama model dan skill
  L.byId['btnMulai'].onclick(); await tunggu(40);
  const b = JSON.parse(L.panggilan.find(p => p.url === '/api/model/pilih').body);
  assert.strictEqual(b.model, 'B'); assert.same(b.skill, ['tanpa']); assert.same(b.prompt, ['bawaan', 'p00000002']);

  // --- 8. Ubah membuka panel lagi
  L.byId['btnPromptUbah'].onclick(); assert.strictEqual(L.byId['promptBox'].hidden, false); assert.strictEqual(L.byId['langkahModel'].hidden, true);
  assert.strictEqual(L.lemari['aa_prompt_selesai'], undefined);

  // --- 9. skill lain di samping Tanpa dengan akses sistem: panel hilang dan prompt tidak dikirim
  L.skillBtn[3].onclick(); await tunggu(20);                                   // tambah Kompleks
  assert.strictEqual(L.byId['promptBox'].hidden, true); assert.strictEqual(L.byId['langkahModel'].hidden, false);
  // (dan ketika dimulai dengan skill seperti itu, id prompt memang tidak dikirim)
  L = lingkungan({lemari: {skill: JSON.stringify(['tanpa', 'kompleks']), aa_model_pilih: 'A', aa_prompt_pilih: JSON.stringify(['bawaan'])}}); await tunggu(60);
  assert.strictEqual(L.byId['promptBox'].hidden, true); assert.strictEqual(L.panggilan.filter(p => p.url === '/api/prompt').length, 0);
  L.byId['btnMulai'].onclick(); await tunggu(30);
  const b2 = JSON.parse(L.panggilan.find(p => p.url === '/api/model/pilih').body);
  assert.same(b2.skill, ['tanpa', 'kompleks']); assert.ok(!('prompt' in b2), 'prompt tidak dikirim bila skill punya akses sistem');

  // --- 10. kunjungan berikutnya: pilihan dan "Selesai" diingat, langsung ringkas
  const tersimpan = [{id: 'bawaan', nama: 'Bawaan (asisten ramah)', isi: 'x', bawaan: true}, {id: 'p00000009', nama: 'Puitis', isi: 'Jawab berpuisi.', bawaan: false}];
  L = lingkungan({lemari: {skill: JSON.stringify(['tanpa']), aa_prompt_pilih: JSON.stringify(['p00000009']), aa_prompt_selesai: '1'}, prompt: tersimpan}); await tunggu(80);
  assert.strictEqual(L.byId['promptBox'].hidden, true); assert.strictEqual(L.byId['promptRingkas'].hidden, false);
  assert.strictEqual(L.byId['promptRingkasTeks'].textContent, 'Prompt: Puitis'); assert.strictEqual(L.byId['langkahModel'].hidden, false);
  // pilihan yang sudah dihapus dari server dilepas; semuanya hilang = murni (bukan bawaan)
  L = lingkungan({lemari: {skill: JSON.stringify(['tanpa']), aa_prompt_pilih: JSON.stringify(['p0000dead']), aa_prompt_selesai: '1'}}); await tunggu(80);
  assert.strictEqual(L.byId['promptRingkasTeks'].textContent, 'Prompt: tanpa prompt (murni)');
  // pilihan kosong yang tersimpan tetap kosong (tidak dikembalikan ke bawaan)
  L = lingkungan({lemari: {skill: JSON.stringify(['tanpa']), aa_prompt_pilih: '[]'}}); await tunggu(80);
  assert.strictEqual(cek(baris(L)[0]).checked, false);

  // --- 11. daftar gagal dimuat: pesan jelas dan alur tetap bisa dilanjutkan
  L = lingkungan({lemari: {skill: JSON.stringify(['tanpa'])}, galatDaftar: true}); await tunggu(80);
  assert.ok(L.byId['promptKet'].textContent.startsWith('Gagal memuat daftar prompt: server rusak'), L.byId['promptKet'].textContent);
  L.byId['btnPromptSelesai'].onclick(); assert.strictEqual(L.byId['langkahModel'].hidden, false);
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
