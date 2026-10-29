// Tes asap panel prompt untuk skill Tanpa (web/prompt.js + index.js) dengan DOM dan fetch tiruan (butuh node).
// Dipakai oleh tests/test_prompt.py.
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
assert.same = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);
const web = f => fs.readFileSync(path.join(__dirname, '..', 'web', f), 'utf8');

function lingkungan(opsi) {
  const byId = {}, panggilan = [], lemari = Object.assign({aa_token: 'TOK'}, opsi.lemari || {});
  const unduhan = [];
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
      click() { if (this.tag === 'a' && this.download) unduhan.push({nama: this.download, href: this.href}); }, files: [],
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
  const respon = (k, obj) => ({ok: k < 400, status: k, json: async () => obj, blob: async () => ({ukuran: 7})});
  let nomor = 1;
  async function fetchPalsu(url, o) {
    o = o || {}; panggilan.push({url, metode: o.method || 'GET', body: o.body});
    if (url === '/api/status') return respon(200, status());
    if (url === '/api/model/pilih') { opsi.status = {status: 'memuat', pesan: 'Memuat ...'}; return respon(200, {ok: true}); }
    if (url === '/api/prompt' && !o.method) return opsi.galatDaftar ? respon(500, {error: 'server rusak'}) : respon(200, {prompt, bawaan: 'bawaan', abaikan: opsi.abaikan || []});
    if (url.startsWith('/api/prompt/ekspor?')) { const id = new URLSearchParams(url.split('?')[1]).get('id'); return prompt.some(p => p.id === id && !p.bawaan) ? respon(200, {}) : respon(404, {error: 'Prompt tidak ditemukan'}); }
    if (url === '/api/prompt/impor') {
      let d; try { d = JSON.parse(JSON.parse(o.body).teks); } catch (e) { return respon(400, {error: 'Bukan berkas JSON yang valid'}); }
      const baru = [], dilewati = [];
      for (const x of (Array.isArray(d) ? d : [d])) {
        if (prompt.some(p => p.isi === x.isi)) { dilewati.push({nama: x.nama, alasan: 'sudah ada (isinya sama)'}); continue; }
        const b = {id: 'p0000000' + (nomor++), nama: x.nama, isi: x.isi, catatan: x.catatan || '', bawaan: false}; prompt.push(b); baru.push(b);
      }
      return respon(200, {ok: true, baru, dilewati, prompt});
    }
    if (url === '/api/prompt' && o.method === 'POST') {
      const b = JSON.parse(o.body);
      if (prompt.some(p => p.nama.toLowerCase() === b.nama.toLowerCase())) return respon(400, {error: 'Sudah ada prompt dengan nama itu'});
      const baru = {id: 'p0000000' + (nomor++), nama: b.nama, isi: b.isi, catatan: b.catatan || '', bawaan: false}; prompt.push(baru);
      return respon(200, {ok: true, baru, prompt});
    }
    if (url === '/api/prompt/ubah') {
      const b = JSON.parse(o.body), p = prompt.find(x => x.id === b.id);
      if (!p || p.bawaan) return respon(404, {error: 'Prompt tidak ditemukan'});
      if (prompt.some(x => x.id !== b.id && x.nama.toLowerCase() === b.nama.toLowerCase())) return respon(400, {error: 'Sudah ada prompt dengan nama itu'});
      p.nama = b.nama; p.isi = b.isi; if (typeof b.catatan === 'string') p.catatan = b.catatan; return respon(200, {ok: true, baru: p, prompt});
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
    URL: {createObjectURL: () => 'blob:x', revokeObjectURL() {}},
    location: {search: '', pathname: '/', hash: ''}, history: {replaceState() {}}, URLSearchParams, navigator: {clipboard: null},
    requestAnimationFrame: f => f(), TextDecoder, TextEncoder, Intl, Date, JSON, Math, Promise, Set, Map,
  };
  konteks.window.localStorage = konteks.localStorage; konteks.window.document = document;
  vm.createContext(konteks);
  vm.runInContext(web('prompt.js'), konteks); vm.runInContext(web('index.js'), konteks);
  return {byId, panggilan, lemari, skillBtn, prompt, unduhan, setKonfirmasi: v => { konfirmasi = v; }};
}
const tunggu = ms => new Promise(r => setTimeout(r, ms));
const baris = L => L.byId['promptList'].children;                       // tiap baris: [label(cek, nama), tombol hapus?]
const cek = b => b.children[0].children[0];
const namaBaris = b => b.children[0].children[1].textContent;
const ubahBtn = b => b.children[1];
const eksporBtn = b => b.children[2];
const hapusBtn = b => b.children[3];
const kelas = e => ' ' + e.className + ' ';
function teks_(e) { return [e._text].concat(e.children.map(teks_)).join('|'); }

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
  assert.ok(ubahBtn(baris(L)[0]).attrs['aria-label'].includes('Salin prompt bawaan'), 'bawaan: tombol salin');
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
  assert.same(JSON.parse(L.panggilan.find(p => p.url === '/api/prompt' && p.metode === 'POST').body), {nama: 'Penerjemah', isi: 'Terjemahkan ke Inggris.', catatan: ''});
  assert.strictEqual(baris(L).length, 2); assert.strictEqual(namaBaris(baris(L)[1]), 'Penerjemah');
  assert.strictEqual(cek(baris(L)[1]).checked, true, 'prompt baru langsung dicentang');
  assert.strictEqual(form.hidden, true); assert.strictEqual(L.byId['promptNama'].value, ''); assert.strictEqual(L.byId['promptIsi'].value, '');
  assert.strictEqual(hapusBtn(baris(L)[1]).textContent, '(−)'); assert.strictEqual(ubahBtn(baris(L)[1]).textContent, '(✎)'); assert.strictEqual(eksporBtn(baris(L)[1]).textContent, '(⬇)');
  assert.strictEqual(baris(L)[0].children.length, 2, 'bawaan: hanya salin, tanpa unduh dan hapus');
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

  // --- 5b. ubah prompt: form terisi, id dan centang tetap, nama boleh diganti
  const ubahPost = () => L.panggilan.filter(p => p.url === '/api/prompt/ubah');
  ubahBtn(baris(L)[1]).onclick();
  assert.strictEqual(L.byId['promptForm'].hidden, false); assert.strictEqual(L.byId['promptFormJudul'].textContent, 'Ubah prompt: Singkat');
  assert.strictEqual(L.byId['promptNama'].value, 'Singkat'); assert.strictEqual(L.byId['promptIsi'].value, 'Jawab satu kalimat.');
  L.byId['promptIsi'].value = 'Jawab dua kalimat.'; L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.same(JSON.parse(ubahPost()[0].body), {id: 'p00000002', nama: 'Singkat', isi: 'Jawab dua kalimat.', catatan: ''});
  assert.strictEqual(L.byId['promptForm'].hidden, true); assert.strictEqual(namaBaris(baris(L)[1]), 'Singkat');
  assert.strictEqual(cek(baris(L)[1]).checked, true, 'centang tetap setelah diubah'); assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), ['bawaan', 'p00000002']);
  assert.strictEqual(L.prompt.find(p => p.id === 'p00000002').isi, 'Jawab dua kalimat.');
  ubahBtn(baris(L)[1]).onclick(); L.byId['promptNama'].value = 'Ringkas'; L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.strictEqual(namaBaris(baris(L)[1]), 'Ringkas'); assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), ['bawaan', 'p00000002']);
  // validasi dan galat server tampil di form yang tetap terbuka
  ubahBtn(baris(L)[1]).onclick(); L.byId['promptNama'].value = ''; L.byId['btnPromptSimpan'].onclick(); await tunggu(10);
  assert.strictEqual(L.byId['promptGalat'].textContent, 'Nama prompt wajib diisi.'); assert.strictEqual(ubahPost().length, 2, 'tidak ada yang dikirim');
  L.byId['promptNama'].value = 'bawaan (asisten ramah)'; L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.strictEqual(L.byId['promptGalat'].textContent, 'Sudah ada prompt dengan nama itu'); assert.strictEqual(L.byId['promptForm'].hidden, false);
  // Batal: tutup tanpa menyimpan, kolom dibersihkan
  L.byId['promptNama'].value = 'Sementara'; L.byId['btnPromptBatal'].onclick();
  assert.strictEqual(L.byId['promptForm'].hidden, true); assert.strictEqual(L.byId['promptNama'].value, ''); assert.strictEqual(ubahPost().length, 3, 'Batal tidak mengirim apa pun');
  assert.strictEqual(namaBaris(baris(L)[1]), 'Ringkas');
  // + prompt sesudah mengubah: kembali ke mode baru dengan kolom kosong
  ubahBtn(baris(L)[1]).onclick(); L.byId['btnPromptBaru'].onclick();
  assert.strictEqual(L.byId['promptFormJudul'].textContent, 'Prompt baru'); assert.strictEqual(L.byId['promptNama'].value, ''); assert.strictEqual(L.byId['promptIsi'].value, '');
  L.byId['btnPromptBaru'].onclick(); assert.strictEqual(L.byId['promptForm'].hidden, true, 'ketuk + prompt lagi menutup');
  // Bawaan tidak bisa diubah: tombolnya membuat SALINAN (prompt baru), bukan mengubah bawaan
  ubahBtn(baris(L)[0]).onclick();
  assert.ok(L.byId['promptFormJudul'].textContent.startsWith('Salinan dari prompt bawaan')); assert.strictEqual(L.byId['promptNama'].value, 'Salinan bawaan');
  assert.strictEqual(L.byId['promptIsi'].value, 'Kamu asisten. {waktu}');
  L.byId['promptIsi'].value = 'Kamu asisten yang lucu. {waktu}'; L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.strictEqual(ubahPost().length, 3, 'salinan dibuat lewat /api/prompt, bukan /ubah');
  assert.same(JSON.parse(L.panggilan.filter(p => p.url === '/api/prompt' && p.metode === 'POST').pop().body), {nama: 'Salinan bawaan', isi: 'Kamu asisten yang lucu. {waktu}', catatan: ''});
  assert.strictEqual(baris(L).length, 3); assert.strictEqual(L.prompt[0].isi, 'Kamu asisten. {waktu}', 'bawaan tidak berubah');
  hapusBtn(baris(L)[2]).onclick(); await tunggu(40);                                          // rapikan: hapus salinan dan kembalikan nama
  ubahBtn(baris(L)[1]).onclick(); L.byId['promptNama'].value = 'Singkat'; L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.same(JSON.parse(L.lemari['aa_prompt_pilih']), ['bawaan', 'p00000002']);

  // --- 5c. catatan: opsional, tampil di daftar, ikut disimpan dan diisikan lagi saat diubah
  L.byId['btnPromptBaru'].onclick(); L.byId['promptNama'].value = 'Formal'; L.byId['promptIsi'].value = 'Jawab formal.'; L.byId['promptCatatan'].value = 'uji di 3B';
  L.byId['btnPromptSimpan'].onclick(); await tunggu(40);
  assert.same(JSON.parse(L.panggilan.filter(p => p.url === '/api/prompt' && p.metode === 'POST').pop().body), {nama: 'Formal', isi: 'Jawab formal.', catatan: 'uji di 3B'});
  const barisFormal = baris(L).find(b => namaBaris(b).startsWith('Formal'));
  assert.ok(teks_(barisFormal).includes('uji di 3B'), 'catatan tampil di bawah nama'); assert.ok(barisFormal.children[0].title.startsWith('uji di 3B'));
  assert.strictEqual(L.byId['promptCatatan'].value, '', 'kolom catatan dibersihkan setelah simpan');
  ubahBtn(barisFormal).onclick(); assert.strictEqual(L.byId['promptCatatan'].value, 'uji di 3B', 'ubah: catatan terisi'); L.byId['btnPromptBatal'].onclick();
  ubahBtn(baris(L)[0]).onclick(); assert.strictEqual(L.byId['promptCatatan'].value, '', 'salin bawaan: tanpa catatan'); L.byId['btnPromptBatal'].onclick();

  // --- 5d. ekspor: unduh berkas .json lewat fetch berotorisasi (bawaan tidak punya tombol unduh)
  L.unduhan.length = 0; eksporBtn(baris(L)[2]).onclick(); await tunggu(40);                          // urutan: bawaan, Formal, Singkat? cari yang benar di bawah
  const idx = baris(L).findIndex(b => namaBaris(b).startsWith('Singkat'));
  eksporBtn(baris(L)[idx]).onclick(); await tunggu(40);
  const ek = L.panggilan.filter(p => p.url.startsWith('/api/prompt/ekspor?')).pop();
  assert.strictEqual(ek.url, '/api/prompt/ekspor?id=p00000002');
  assert.ok(L.unduhan.some(u => u.nama === 'p00000002.json'), 'berkas .json terunduh');
  assert.ok(L.byId['promptKet'].textContent.startsWith('Diunduh: p00000002.json'), L.byId['promptKet'].textContent);

  // --- 5e. impor: beberapa berkas sekaligus; yang gagal dan yang kembar dilaporkan; hasil impor tidak otomatis dicentang
  const sebelum = L.lemari['aa_prompt_pilih'];
  L.byId['promptBerkas'].files = [
    {name: 'a.json', text: async () => JSON.stringify({format: 'ai-asisten-prompt', nama: 'Dari Teman', isi: 'Jawab puitis.', catatan: 'uji'})},
    {name: 'b.json', text: async () => '{rusak'},
    {name: 'c.json', text: async () => JSON.stringify([{nama: 'Kembar', isi: 'Jawab puitis.'}])}];
  L.byId['btnPromptImpor'].onclick(); L.byId['promptBerkas'].onchange(); await tunggu(80);
  assert.strictEqual(L.panggilan.filter(p => p.url === '/api/prompt/impor').length, 3);
  assert.ok(baris(L).some(b => namaBaris(b).startsWith('Dari Teman')), 'prompt impor muncul di daftar');
  assert.strictEqual(L.lemari['aa_prompt_pilih'], sebelum, 'impor tidak mengubah centang');
  const ket = L.byId['promptKet'].textContent;
  assert.ok(ket.startsWith('Impor: 1 prompt ditambahkan, 2 dilewati ('), ket);
  assert.ok(ket.includes('b.json: Bukan berkas JSON yang valid') && ket.includes('Kembar: sudah ada (isinya sama)'), ket);
  const dt = baris(L).find(b => namaBaris(b).startsWith('Dari Teman')); hapusBtn(dt).onclick(); await tunggu(40);          // rapikan
  hapusBtn(baris(L).find(b => namaBaris(b).startsWith('Formal'))).onclick(); await tunggu(40);
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

  // --- 10b. berkas di folder prompt yang tidak valid dilaporkan di bawah daftar
  L = lingkungan({lemari: {skill: JSON.stringify(['tanpa'])}, abaikan: [{berkas: 'rusak.json', alasan: 'bukan JSON yang valid'}, {berkas: 'b.json', alasan: 'x'}, {berkas: 'c.json', alasan: 'y'}]}); await tunggu(80);
  assert.ok(L.byId['promptKet'].textContent.includes('3 berkas di folder prompt dilewati (tidak valid: rusak.json, b.json ...)'), L.byId['promptKet'].textContent);

  // --- 11. daftar gagal dimuat: pesan jelas dan alur tetap bisa dilanjutkan
  L = lingkungan({lemari: {skill: JSON.stringify(['tanpa'])}, galatDaftar: true}); await tunggu(80);
  assert.ok(L.byId['promptKet'].textContent.startsWith('Gagal memuat daftar prompt: server rusak'), L.byId['promptKet'].textContent);
  L.byId['btnPromptSelesai'].onclick(); assert.strictEqual(L.byId['langkahModel'].hidden, false);
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
