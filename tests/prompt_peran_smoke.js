// Tes asap panel prompt per peran Agent (web/prompt_peran.js) dengan DOM dan fetch tiruan (butuh node).
// Dipakai oleh tests/test_peran.py.
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
assert.same = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);
const kode = fs.readFileSync(path.join(__dirname, '..', 'web', 'prompt_peran.js'), 'utf8');

function mk(tag, unduhan) {
  const e = {
    tag, children: [], className: '', _text: '', hidden: false, value: '', attrs: {}, title: '', type: '', checked: false, disabled: false,
    onclick: null, onchange: null, parentElement: null, classes: new Set(), files: [], download: '', href: '',
    get textContent() { return this._text; }, set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(n) { if (n && typeof n === 'object') n.parentElement = this; this.children.push(n); return n; },
    append(...n) { n.forEach(x => this.appendChild(x)); }, remove() {}, focus() { this.difokus = true; },
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    click() { if (this.tag === 'a' && this.download) unduhan.push({nama: this.download, href: this.href}); if (this.tag === 'input' && this.type === 'file') this.diklik = true; },
  };
  e.classList = {toggle(c, on) { if (on === undefined ? !e.classes.has(c) : on) e.classes.add(c); else e.classes.delete(c); },
    add(c) { e.classes.add(c); }, remove(c) { e.classes.delete(c); }, contains(c) { return e.classes.has(c) || e.className.split(' ').includes(c); }};
  return e;
}
const semuaTurunan = e => e.children.reduce((a, c) => a.concat([c], semuaTurunan(c)), []);
const cari = (e, kelas) => semuaTurunan(e).filter(x => x.className.split(' ').includes(kelas));
const cariTeks = (e, teks) => semuaTurunan(e).filter(x => x._text === teks);

function lingkungan(opsi) {
  opsi = opsi || {};
  const unduhan = [], panggilan = [], diubah = [];
  const gudang = {};                                    // peran -> daftar prompt buatan pengguna
  for (const p of ['perencana', 'pelaksana']) gudang[p] = (opsi.prompt && opsi.prompt[p] || []).map(x => Object.assign({bawaan: false, catatan: ''}, x));
  const label = {perencana: 'Perencana', pelaksana: 'Pelaksana'};
  const daftar = p => [{id: 'bawaan', nama: 'Bawaan (' + label[p] + ')', isi: 'PERILAKU-' + p, catatan: 'Perilaku bawaan.', bawaan: true}].concat(gudang[p]);
  const respon = (k, obj) => ({ok: k < 400, status: k, json: async () => obj, blob: async () => ({ukuran: 7})});
  let nomor = 1, konfirmasi = true;
  async function fetchPalsu(url, o) {
    o = o || {}; const metode = o.method || 'GET';
    panggilan.push({url, metode, body: o.body, auth: (o.headers || {}).Authorization});
    if (opsi.galatDaftar && metode === 'GET' && url.startsWith('/api/agent/prompt?')) return respon(500, {error: 'server rusak'});
    const q = url.includes('?') ? new URLSearchParams(url.split('?')[1]) : new URLSearchParams();
    const b = o.body ? JSON.parse(o.body) : {};
    const p = q.get('peran') || b.peran;
    if (!gudang[p]) return respon(400, {error: 'Peran tidak dikenal'});
    if (url.startsWith('/api/agent/prompt/ekspor?')) return gudang[p].some(x => x.id === q.get('id')) ? respon(200, {}) : respon(404, {error: 'Prompt tidak ditemukan'});
    if (url.startsWith('/api/agent/prompt?')) return respon(200, {peran: p, prompt: daftar(p), bawaan: 'bawaan', abaikan: opsi.abaikan || []});
    if (url === '/api/agent/prompt') {
      if (gudang[p].some(x => x.nama.toLowerCase() === b.nama.toLowerCase())) return respon(400, {error: 'Sudah ada prompt dengan nama itu'});
      const baru = {id: 'p' + (nomor++), nama: b.nama, isi: b.isi, catatan: b.catatan || '', bawaan: false}; gudang[p].push(baru);
      return respon(200, {ok: true, baru, prompt: daftar(p)});
    }
    if (url === '/api/agent/prompt/ubah') {
      const x = gudang[p].find(y => y.id === b.id); if (!x) return respon(404, {error: 'Prompt tidak ditemukan'});
      x.nama = b.nama; x.isi = b.isi; x.catatan = b.catatan || ''; return respon(200, {ok: true, baru: x, prompt: daftar(p)});
    }
    if (url === '/api/agent/prompt/hapus') { const i = gudang[p].findIndex(y => y.id === b.id); if (i >= 0) gudang[p].splice(i, 1); return respon(200, {ok: i >= 0, prompt: daftar(p)}); }
    if (url === '/api/agent/prompt/impor') {
      let d; try { d = JSON.parse(b.teks); } catch (e) { return respon(400, {error: 'Bukan berkas JSON yang valid'}); }
      const baru = [], dilewati = [];
      for (const x of (Array.isArray(d) ? d : [d])) {
        if (gudang[p].some(y => y.isi === x.isi)) { dilewati.push({nama: x.nama, alasan: 'sudah ada (isinya sama)'}); continue; }
        const n = {id: 'p' + (nomor++), nama: x.nama, isi: x.isi, catatan: x.catatan || '', bawaan: false}; gudang[p].push(n); baru.push(n);
      }
      return respon(200, {ok: true, baru, dilewati, prompt: daftar(p)});
    }
    return respon(404, {error: 'tidak ada'});
  }
  const document = {createElement: t => mk(t, unduhan), body: mk('body', unduhan)};
  const konteks = {window: {confirm: () => konfirmasi}, document, console, fetch: fetchPalsu, setTimeout, URL: {createObjectURL: () => 'blob:x', revokeObjectURL() {}}, URLSearchParams, Promise, JSON, Set};
  vm.createContext(konteks);
  vm.runInContext(kode, konteks);
  const PP = konteks.window.PromptPeran;
  function buat(peran, awal) {
    const wadah = mk('div', unduhan);
    const pp = PP.pasang({peran, label: label[peran], wadah, token: () => 'TOK', awal, onUbah: s => diubah.push(Object.assign({peran}, s))});
    const ringkas = cari(wadah, 'pp-teks')[0], panel = cari(wadah, 'pp-panel')[0], buka = cari(wadah, 'pp-buka')[0];
    return {pp, wadah, ringkas, panel, buka, baris: () => cari(wadah, 'pp-baris'), form: cari(wadah, 'pp-form')[0], ket: cari(wadah, 'pp-ket')[0],
      ketMode: cari(wadah, 'pp-ketmode')[0], modeBtn: cari(wadah, 'pp-modebtn'), daftarEl: cari(wadah, 'pp-daftar')[0]};
  }
  return {PP, buat, gudang, panggilan, diubah, unduhan, setKonfirmasi: v => { konfirmasi = v; }};
}
const tunggu = ms => new Promise(r => setTimeout(r, ms));
const cekBaris = b => b.children[0].children[0];                      // checkbox di <label>
const namaBaris = b => b.children[0].children[b.children[0].children.length - 1]._text;
const tombol = (b, teks) => b.children.find(x => x._text === teks);
const isiForm = (t, nama, isi, catatan) => {
  const [inNama, inIsi, inCat] = semuaTurunan(t.form).filter(x => x.tag === 'input' || x.tag === 'textarea');
  inNama.value = nama; inIsi.value = isi; inCat.value = catatan || '';
};
const klikSimpan = t => semuaTurunan(t.form).find(x => x._text === 'Simpan').onclick();

(async () => {
  // --- 1. keadaan awal: ringkasan "bawaan", panel tertutup, belum ada permintaan ke server
  let L = lingkungan({}), t = L.buat('perencana');
  assert.strictEqual(t.ringkas._text, 'Prompt: bawaan'); assert.strictEqual(t.panel.hidden, true);
  assert.strictEqual(t.buka._text, '+ prompt'); assert.strictEqual(L.panggilan.length, 0);

  // --- 2. membuka panel memuat daftar peran itu (sekali) dan menampilkan Bawaan tanpa kotak centang
  t.buka.onclick(); await tunggu(20);
  assert.strictEqual(t.panel.hidden, false); assert.strictEqual(t.buka._text, 'Tutup');
  assert.same(L.panggilan.map(p => [p.metode, p.url, p.auth]), [['GET', '/api/agent/prompt?peran=perencana', 'Bearer TOK']]);
  assert.strictEqual(t.baris().length, 1);
  assert.ok(/^Bawaan \(Perencana\) · aktif$/.test(namaBaris(t.baris()[0])), namaBaris(t.baris()[0]));
  assert.ok(!semuaTurunan(t.baris()[0]).some(x => x.tag === 'input'), 'Bawaan tidak punya kotak centang');
  assert.ok(/tidak ada yang dicentang/i.test(t.ket._text) && /prompt bawaannya apa adanya/.test(t.ket._text));
  t.buka.onclick(); t.buka.onclick(); await tunggu(5);
  assert.strictEqual(L.panggilan.length, 1, 'daftar tidak diminta ulang setiap panel dibuka');

  // --- 3. lihat isi bawaan dengan mengetuk namanya
  t.baris()[0].children[0].onclick();
  assert.ok(cari(t.daftarEl, 'pp-lihat').some(x => x._text === 'PERILAKU-perencana'));
  t.baris()[0].children[0].onclick();
  assert.strictEqual(cari(t.daftarEl, 'pp-lihat').length, 0);

  // --- 4. "+ prompt": simpan prompt baru -> langsung dicentang, kabar ke halaman, ringkasan berubah
  semuaTurunan(t.wadah).find(x => x._text === '+ prompt' && x.className === 'btn abu kecil').onclick();
  assert.strictEqual(t.form.hidden, false);
  isiForm(t, '  ', 'isi'); klikSimpan(t); await tunggu(5);
  assert.strictEqual(cari(t.form, 'galat')[0]._text, 'Nama prompt wajib diisi.'); assert.strictEqual(L.panggilan.length, 1, 'tidak dikirim bila nama kosong');
  isiForm(t, 'Rencana Rapi', '   '); klikSimpan(t); await tunggu(5);
  assert.strictEqual(cari(t.form, 'galat')[0]._text, 'Isi prompt wajib diisi.');
  isiForm(t, 'Rencana Rapi', 'Rencanakan dengan rapi.', 'cocok model kecil'); klikSimpan(t); await tunggu(20);
  assert.same(JSON.parse(L.panggilan[L.panggilan.length - 1].body), {peran: 'perencana', nama: 'Rencana Rapi', isi: 'Rencanakan dengan rapi.', catatan: 'cocok model kecil'});
  assert.strictEqual(t.form.hidden, true); assert.strictEqual(t.baris().length, 2);
  assert.same(L.diubah[L.diubah.length - 1], {peran: 'perencana', ids: ['p1'], mode: 'tambah'});
  assert.strictEqual(t.ringkas._text, 'Prompt: bawaan + Rencana Rapi');
  assert.strictEqual(cekBaris(t.baris()[1]).checked, true, 'prompt baru langsung dicentang');
  assert.ok(/Dipilih: 1 prompt/.test(t.ket._text));

  // --- 5. nama kembar ditolak server dan pesannya tampil di form
  semuaTurunan(t.wadah).find(x => x._text === '+ prompt' && x.className === 'btn abu kecil').onclick();
  isiForm(t, 'rencana rapi', 'lain'); klikSimpan(t); await tunggu(20);
  assert.strictEqual(cari(t.form, 'galat')[0]._text, 'Sudah ada prompt dengan nama itu'); assert.strictEqual(t.form.hidden, false);
  semuaTurunan(t.form).find(x => x._text === 'Batal').onclick(); assert.strictEqual(t.form.hidden, true);

  // --- 6. mode "ganti"
  assert.ok(/menambahkan di bawahnya|ditambahkan di bawahnya/.test(t.ketMode._text));
  t.modeBtn.find(b => b._text === 'Ganti bawaan').onclick();
  assert.same(L.diubah[L.diubah.length - 1], {peran: 'perencana', ids: ['p1'], mode: 'ganti'});
  assert.strictEqual(t.ringkas._text, 'Prompt: ganti: Rencana Rapi');
  assert.ok(/menggantikan perilaku bawaan Perencana/.test(t.ketMode._text) && /Format keluaran yang dibaca program tetap ditambahkan/.test(t.ketMode._text));
  assert.ok(/diganti$/.test(namaBaris(t.baris()[0])), 'bawaan ditandai diganti');
  assert.strictEqual(t.modeBtn[1].attrs['aria-checked'], 'true'); assert.strictEqual(t.modeBtn[0].attrs['aria-checked'], 'false');

  // --- 7. mencentang / melepas centang
  let cek = cekBaris(t.baris()[1]); cek.checked = false; cek.onchange();
  assert.same(L.diubah[L.diubah.length - 1], {peran: 'perencana', ids: [], mode: 'ganti'});
  assert.strictEqual(t.ringkas._text, 'Prompt: bawaan'); assert.ok(/aktif$/.test(namaBaris(t.baris()[0])), 'tidak ada yang dicentang: bawaan aktif lagi');
  cek = cekBaris(t.baris()[1]); cek.checked = true; cek.onchange();
  assert.same(L.diubah[L.diubah.length - 1].ids, ['p1']);

  // --- 8. ubah prompt (id tetap, centang tetap) dan salin dari bawaan
  tombol(t.baris()[1], '(✎)').onclick();
  assert.strictEqual(t.form.hidden, false); assert.ok(/Ubah prompt: Rencana Rapi/.test(cari(t.form, 'pp-formjudul')[0]._text));
  let [inNama, inIsi, inCat] = semuaTurunan(t.form).filter(x => x.tag === 'input' || x.tag === 'textarea');
  assert.same([inNama.value, inIsi.value, inCat.value], ['Rencana Rapi', 'Rencanakan dengan rapi.', 'cocok model kecil']);
  inNama.value = 'Rencana Super'; klikSimpan(t); await tunggu(20);
  assert.strictEqual(L.panggilan[L.panggilan.length - 1].url, '/api/agent/prompt/ubah');
  assert.strictEqual(L.gudang.perencana[0].nama, 'Rencana Super'); assert.strictEqual(t.baris().length, 2);
  assert.same(L.diubah[L.diubah.length - 1].ids, ['p1'], 'centang tetap sesudah ubah');
  tombol(t.baris()[0], '(✎)').onclick();
  [inNama, inIsi] = semuaTurunan(t.form).filter(x => x.tag === 'input' || x.tag === 'textarea');
  assert.strictEqual(inNama.value, 'Salinan bawaan Perencana'); assert.strictEqual(inIsi.value, 'PERILAKU-perencana', 'salinan berisi perilaku bawaan (tanpa format keluaran)');
  semuaTurunan(t.form).find(x => x._text === 'Batal').onclick();

  // --- 9. ekspor: unduh berkas per peran
  tombol(t.baris()[1], '(⬇)').onclick(); await tunggu(20);
  assert.strictEqual(L.panggilan[L.panggilan.length - 1].url, '/api/agent/prompt/ekspor?peran=perencana&id=p1');
  assert.same(L.unduhan.map(u => u.nama), ['perencana-p1.json']); assert.ok(/Diunduh: perencana-p1.json/.test(t.ket._text));
  assert.ok(!tombol(t.baris()[0], '(⬇)') && !tombol(t.baris()[0], '(−)'), 'bawaan tidak bisa diunduh atau dihapus');

  // --- 10. impor beberapa berkas: yang sama dilewati, yang rusak dilaporkan
  const berkas = semuaTurunan(t.wadah).find(x => x.tag === 'input' && x.type === 'file');
  assert.strictEqual(berkas.accept, '.json,application/json'); assert.strictEqual(berkas.multiple, true);
  semuaTurunan(t.wadah).find(x => x._text === '⬆ Impor').onclick(); assert.strictEqual(berkas.diklik, true);
  berkas.files = [{name: 'a.json', text: async () => JSON.stringify({nama: 'Dari Teman', isi: 'isi teman'})},
    {name: 'b.json', text: async () => JSON.stringify({nama: 'Sama', isi: 'isi teman'})}, {name: 'c.json', text: async () => '{rusak'}];
  berkas.onchange(); await tunggu(40);
  assert.ok(/Impor: 1 prompt ditambahkan, 2 dilewati/.test(t.ket._text), t.ket._text);
  assert.ok(/sudah ada \(isinya sama\)/.test(t.ket._text) && /c\.json: Bukan berkas JSON yang valid/.test(t.ket._text));
  assert.strictEqual(t.baris().length, 3); assert.same(L.panggilan.filter(p => p.url.endsWith('/impor')).map(p => JSON.parse(p.body).peran), ['perencana', 'perencana', 'perencana']);

  // --- 11. hapus: batal tidak menghapus; setuju menghapus dan melepas centangnya
  L.setKonfirmasi(false); const sebelum = L.panggilan.length;
  tombol(t.baris()[1], '(−)').onclick(); await tunggu(10);
  assert.strictEqual(L.panggilan.length, sebelum); assert.strictEqual(t.baris().length, 3);
  L.setKonfirmasi(true); tombol(t.baris()[1], '(−)').onclick(); await tunggu(20);
  assert.strictEqual(L.panggilan[L.panggilan.length - 1].url, '/api/agent/prompt/hapus'); assert.strictEqual(t.baris().length, 2);
  assert.same(L.diubah[L.diubah.length - 1].ids, [], 'prompt yang dihapus dilepas dari pilihan');
  assert.strictEqual(t.ringkas._text, 'Prompt: bawaan');

  // --- 12. "Selesai" menutup panel dan form
  semuaTurunan(t.wadah).find(x => x._text === '+ prompt' && x.className === 'btn abu kecil').onclick();
  semuaTurunan(t.wadah).find(x => x._text === 'Selesai').onclick();
  assert.strictEqual(t.panel.hidden, true); assert.strictEqual(t.form.hidden, true); assert.strictEqual(t.buka._text, '+ prompt');

  // --- 13. pilihan tersimpan dipulihkan; id yang sudah hilang di server dilepas saat daftar dimuat
  L = lingkungan({prompt: {pelaksana: [{id: 'kode', nama: 'Kode', isi: 'k'}]}});
  t = L.buat('pelaksana', {ids: ['kode', 'hilang'], mode: 'ganti'});
  assert.strictEqual(t.ringkas._text, 'Prompt: 2 prompt', 'sebelum daftar dimuat: hanya jumlah');
  await t.pp.muat(); await tunggu(10);
  assert.same(L.diubah, [{peran: 'pelaksana', ids: ['kode'], mode: 'ganti'}]);
  assert.strictEqual(t.ringkas._text, 'Prompt: ganti: Kode'); assert.strictEqual(t.pp.mode(), 'ganti');
  assert.same(L.panggilan.map(p => p.url), ['/api/agent/prompt?peran=pelaksana']);

  // --- 14. bentuk awal yang rusak diabaikan
  L = lingkungan({}); t = L.buat('perencana', {ids: [5, 'a', null], mode: 'aneh'});
  assert.same(t.pp.ids(), ['a']); assert.strictEqual(t.pp.mode(), 'tambah');
  t = L.buat('perencana', null); assert.same(t.pp.ids(), []);

  // --- 15. gagal memuat daftar: pesan galat tampil, bukan diam
  L = lingkungan({galatDaftar: true}); t = L.buat('perencana'); t.buka.onclick(); await tunggu(20);
  assert.ok(/Gagal memuat daftar prompt: server rusak/.test(t.ket._text), t.ket._text);

  // --- 16. berkas yang dilewati server dilaporkan
  L = lingkungan({abaikan: [{berkas: 'rusak.json', alasan: 'bukan JSON yang valid'}]}); t = L.buat('perencana'); t.buka.onclick(); await tunggu(20);
  assert.ok(/1 berkas di folder peran ini dilewati \(tidak valid: rusak\.json\)/.test(t.ket._text), t.ket._text);

  // --- 17. dua peran memakai daftar dan alamat masing-masing
  L = lingkungan({prompt: {perencana: [{id: 'a', nama: 'A', isi: 'x'}], pelaksana: []}});
  const t1 = L.buat('perencana'), t2 = L.buat('pelaksana'); t1.buka.onclick(); t2.buka.onclick(); await tunggu(20);
  assert.strictEqual(t1.baris().length, 2); assert.strictEqual(t2.baris().length, 1);
  assert.same(L.panggilan.map(p => p.url).sort(), ['/api/agent/prompt?peran=pelaksana', '/api/agent/prompt?peran=perencana']);

  // --- 18. peringatan panjang
  L = lingkungan({prompt: {perencana: [{id: 'a', nama: 'A', isi: 'x'.repeat(3500)}, {id: 'b', nama: 'B', isi: 'y'.repeat(3000)}]}});
  t = L.buat('perencana', {ids: ['a'], mode: 'tambah'}); t.buka.onclick(); await tunggu(20);
  assert.ok(/panjang: memakan konteks/.test(t.ket._text), t.ket._text);
  cek = cekBaris(t.baris()[2]); cek.checked = true; cek.onchange();
  assert.ok(/terlalu panjang: kurangi/.test(t.ket._text), t.ket._text);

  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
