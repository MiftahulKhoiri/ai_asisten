// Tes asap dialog Pengaturan koneksi (web/koneksi.js) dengan DOM dan fetch tiruan (butuh node).
// Dipakai oleh tests/test_koneksi.py.
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
const kode = fs.readFileSync(path.join(__dirname, '..', 'web', 'koneksi.js'), 'utf8');

function mk(tag) {
  const e = {
    tag, children: [], className: '', _text: '', hidden: false, value: '', attrs: {}, dataset: {}, disabled: false,
    onclick: null, handlers: {}, id: '', type: '', placeholder: '', title: '', classes: new Set(),
    get textContent() { return this._text + this.children.map(c => (typeof c === 'string' ? c : c.textContent)).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(n) { this.children.push(n); return n; },
    append(...n) { n.forEach(x => this.children.push(x)); },
    setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(t, f) { this.handlers[t] = f; }, focus() { this.focado = true; },
  };
  e.classList = {toggle(c, on) { if (on) e.classes.add(c); else e.classes.delete(c); }, add(c) { e.classes.add(c); },
    contains(c) { return e.classes.has(c); }};
  return e;
}
function cari(e, f) {
  if (typeof e === 'string') return null;
  if (f(e)) return e;
  for (const c of e.children) { const r = cari(c, f); if (r) return r; }
  return null;
}

function ringkas(extra) {
  const daftar = [{id: 'lokal', nama: 'llama-server', jenis: 'llama', alamat: 'http://127.0.0.1:8080', key_ada: false, utama: true,
    peringatan: '', ok: true, jumlah: 3, galat: ''}].concat(extra || []);
  const u = daftar[0];
  return {alamat: u.alamat, jenis: u.jenis, key_ada: u.key_ada, nama: u.nama, sumber: 'web', peringatan: u.peringatan, daftar, maks_tambahan: 8};
}
const ONLINE = {id: 'kabc123', nama: 'OpenRouter', jenis: 'online', alamat: 'https://openrouter.ai/api/v1', key_ada: true, utama: false,
  peringatan: '', ok: true, jumlah: 40, galat: ''};

function jalankan(extra, awal) {
  const panggilan = [], toasts = [], sesudah = [];
  const body = mk('body');
  const state = Object.assign(ringkas(extra), awal || {});
  const respon = (k, obj) => ({ok: k < 400, status: k, json: async () => obj});
  const jawab = {uji: {ok: true, jumlah: 3, contoh: ['a', 'b', 'c'], router: true, peringatan: ''}, simpan: null, reset: null};
  async function fetchPalsu(url, o) {
    o = o || {};
    panggilan.push({url, metode: o.method || 'GET', body: o.body ? JSON.parse(o.body) : null, auth: (o.headers || {}).Authorization});
    if (url === '/api/koneksi' && o.method !== 'POST') return respon(200, state);
    if (url === '/api/koneksi/uji') return respon(200, jawab.uji);
    if (url === '/api/koneksi') {
      if (jawab.simpan) return jawab.simpan;
      const b = JSON.parse(o.body);
      if (b.id === 'baru') {
        state.daftar.push({id: 'kbaru01', nama: b.nama || 'Baru', jenis: b.jenis, alamat: b.alamat, key_ada: !!b.key, utama: false,
          peringatan: '', ok: true, jumlah: 5, galat: ''});
      } else {
        const c = state.daftar.find(x => x.id === b.id);
        if (b.key === '') c.key_ada = false; else if (b.key) c.key_ada = true;
      }
      return respon(200, {ok: true, tersimpan: true, id: b.id, koneksi: state});
    }
    if (url === '/api/koneksi/hapus') {
      const b = JSON.parse(o.body);
      state.daftar = state.daftar.filter(x => x.id !== b.id);
      return respon(200, {ok: true, koneksi: state});
    }
    if (url === '/api/koneksi/reset') return jawab.reset || respon(200, {ok: true, koneksi: state});
    return respon(404, {});
  }
  const document = {createElement: mk, body, getElementById: () => mk('div')};
  const ctx = {document, window: {}, fetch: fetchPalsu, confirm: () => true, console, setTimeout, clearTimeout, JSON};
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(kode, ctx);
  const wadah = mk('div');
  const k = ctx.Koneksi.pasang({token: () => 'TOK', wadah, toast: m => toasts.push(m), setelahUbah: x => sesudah.push(x)});
  return {k, wadah, panggilan, toasts, sesudah, body, state, jawab,
    dlg: () => cari(body, e => e.className === 'kon-dlg'),
    tirai: () => cari(body, e => e.className === 'kon-tirai'),
    el: (id) => cari(body, e => e.id === id),
    tombol: (teks) => cari(body, e => e.tag === 'button' && e.textContent === teks),
    item: (id) => cari(body, e => e.className === 'kon-item' && e.dataset.id === id),
    semuaItem: () => { const h = []; (function w(e) { if (typeof e === 'string') return; if (e.className === 'kon-item') h.push(e); e.children.forEach(w); })(body); return h; },
    hasil: () => cari(body, e => /^kon-hasil/.test(e.className))};
}
const tunggu = () => new Promise(r => setTimeout(r, 5));
const jenisSeg = t => t.dlg().children.find(c => c.className && c.className.includes('kon-form')).children.find(c => c.className && c.className.includes('kon-seg'));
const respon409 = () => ({ok: false, status: 409, json: async () => ({ok: false, error: 'Sedang ada proses berjalan. Tunggu selesai atau hentikan dulu.'})});

(async () => {
  // 1. baris ringkas: satu sumber lokal; lalu lokal + online (jenis tertulis, key tidak)
  let t = jalankan();
  t.k.perbarui(t.state);
  assert.strictEqual(t.wadah.children[0].textContent, 'Sumber model: llama-server (lokal)');
  t = jalankan([ONLINE]);
  t.k.perbarui(t.state);
  assert.strictEqual(t.wadah.children[0].textContent, 'Sumber model: llama-server (lokal) · OpenRouter (online)');
  const gagal = Object.assign({}, ONLINE, {ok: false, galat: 'Ditolak server (401)'});
  t.k.perbarui(ringkas([gagal]));
  assert.ok(/⚠ OpenRouter \(online\)/.test(t.wadah.children[0].textContent));
  // nama bawaan "Lokal" tidak diulang sebagai "(lokal)"
  t.k.perbarui(ringkas([]).daftar ? Object.assign(ringkas([ONLINE]), {daftar: [Object.assign({}, ringkas().daftar[0], {nama: 'Lokal'}), ONLINE]}) : null);
  assert.strictEqual(t.wadah.children[0].textContent, 'Sumber model: Lokal · OpenRouter (online)');

  // 2. buka: ambil data terbaru, daftar menampilkan SEMUA koneksi dengan badge Lokal/Online, status, dan tanda key
  t = jalankan([ONLINE]);
  await t.k.buka();
  assert.strictEqual(t.panggilan[0].url, '/api/koneksi');
  assert.strictEqual(t.panggilan[0].auth, 'Bearer TOK');
  assert.strictEqual(t.tirai().hidden, false);
  assert.strictEqual(t.semuaItem().length, 2);
  const teksUtama = t.item('lokal').textContent, teksOn = t.item('kabc123').textContent;
  assert.ok(/Lokal/.test(teksUtama) && /utama/.test(teksUtama) && /3 model/.test(teksUtama), teksUtama);
  assert.ok(/Online/.test(teksOn) && /OpenRouter/.test(teksOn) && /API key ✔/.test(teksOn) && /40 model/.test(teksOn), teksOn);
  assert.ok(!/Hapus/.test(teksUtama));                    // koneksi utama tidak bisa dihapus
  assert.ok(/Hapus/.test(teksOn));
  assert.ok(!/sk-/.test(t.dlg().textContent));            // kunci tidak pernah tampil

  // 3. koneksi yang gagal ditandai dengan galatnya
  t = jalankan([gagal]);
  await t.k.buka();
  assert.ok(/⚠ Ditolak server \(401\)/.test(t.item('kabc123').textContent));

  // 4. tambah koneksi online: form kosong, jenis online bawaan; uji tidak membawa id selain "baru"
  t = jalankan();
  await t.k.buka();
  await t.tombol('+ Tambah koneksi').onclick();
  assert.strictEqual(t.el('konAlamat').value, '');
  assert.strictEqual(t.el('konNama').value, '');
  assert.strictEqual(t.el('konKunci').type, 'password');
  t.el('konNama').value = ' OpenRouter ';
  t.el('konAlamat').value = ' https://openrouter.ai/api/v1 ';
  t.el('konKunci').value = ' sk-or-1 '; t.el('konKunci').handlers.input();
  t.jawab.uji = {ok: true, jumlah: 40, contoh: ['x'], router: false, peringatan: ''};
  await t.tombol('Uji koneksi').onclick(); await tunggu();
  let uji = t.panggilan.filter(p => p.url === '/api/koneksi/uji').pop();
  assert.deepStrictEqual(uji.body, {id: 'baru', alamat: 'https://openrouter.ai/api/v1', jenis: 'online', nama: 'OpenRouter', key: 'sk-or-1'});
  assert.ok(/Terhubung · 40 model/.test(t.hasil().textContent) && /Tanpa mode router/.test(t.hasil().textContent));
  await t.tombol('Simpan').onclick(); await tunggu();
  const simpan = t.panggilan.filter(p => p.url === '/api/koneksi' && p.metode === 'POST').pop();
  assert.strictEqual(simpan.body.id, 'baru');
  assert.strictEqual(simpan.body.key, 'sk-or-1');
  assert.strictEqual(t.el('konKunci').value, '');                      // kolom key dikosongkan
  assert.strictEqual(t.semuaItem().length, 2);                         // daftar bertambah
  assert.strictEqual(t.sesudah.length, 1);
  assert.ok(t.toasts.includes('Koneksi disimpan'));
  assert.ok(/OpenRouter \(online\)/.test(t.wadah.textContent));
  assert.ok(!t.wadah.textContent.includes('sk-or-1') && !t.toasts.join(' ').includes('sk-or-1'));

  // 5. ubah koneksi online: terisi dari daftar; tanpa mengetik key -> key tidak dikirim; hapus key tersimpan -> key ''
  t = jalankan([ONLINE]);
  await t.k.buka();
  await t.item('kabc123').children.find(c => c.className && c.className.includes('kon-item-aksi')).children[0].onclick();
  assert.strictEqual(t.el('konAlamat').value, 'https://openrouter.ai/api/v1');
  assert.strictEqual(t.el('konNama').value, 'OpenRouter');
  assert.ok(/tersimpan/.test(t.el('konKunci').placeholder));
  assert.strictEqual(t.tombol('Pakai bawaan').hidden, true);          // hanya koneksi utama punya "Pakai bawaan"
  await t.tombol('Uji koneksi').onclick(); await tunggu();
  uji = t.panggilan.filter(p => p.url === '/api/koneksi/uji').pop();
  assert.strictEqual(uji.body.id, 'kabc123');
  assert.ok(!('key' in uji.body));
  t.tombol('Hapus API key tersimpan').onclick();
  assert.ok(/dihapus saat Simpan/.test(cari(t.body, e => /kon-kunci-ket/.test(e.className)).textContent));
  await t.tombol('Simpan').onclick(); await tunggu();
  const hk = t.panggilan.filter(p => p.url === '/api/koneksi' && p.metode === 'POST').pop();
  assert.strictEqual(hk.body.id, 'kabc123');
  assert.strictEqual(hk.body.key, '');

  // 6. hapus koneksi tambahan: memanggil /api/koneksi/hapus, daftar berkurang, model dimuat ulang (setelahUbah)
  t = jalankan([ONLINE]);
  await t.k.buka();
  const aksi = t.item('kabc123').children.find(c => c.className && c.className.includes('kon-item-aksi'));
  await aksi.children[1].onclick(); await tunggu();
  assert.ok(t.panggilan.some(p => p.url === '/api/koneksi/hapus' && p.body.id === 'kabc123'));
  assert.strictEqual(t.semuaItem().length, 1);
  assert.strictEqual(t.sesudah.length, 1);

  // 7. ubah koneksi utama: bisa "Pakai bawaan" (reset)
  t = jalankan();
  await t.k.buka();
  await t.item('lokal').children.find(c => c.className && c.className.includes('kon-item-aksi')).children[0].onclick();
  assert.strictEqual(t.el('konAlamat').value, 'http://127.0.0.1:8080');
  assert.strictEqual(t.tombol('Pakai bawaan').hidden, false);
  await t.tombol('Pakai bawaan').onclick(); await tunggu();
  assert.ok(t.panggilan.some(p => p.url === '/api/koneksi/reset' && p.metode === 'POST'));
  assert.strictEqual(t.sesudah.length, 1);

  // 8. simpan ditolak server (ada proses berjalan): pesan tampil, form tetap terbuka, setelahUbah tak dipanggil
  t = jalankan();
  await t.k.buka();
  await t.tombol('+ Tambah koneksi').onclick();
  t.el('konAlamat').value = 'https://x.example/v1';
  t.jawab.simpan = respon409();
  await t.tombol('Simpan').onclick(); await tunggu();
  assert.ok(/Sedang ada proses/.test(t.hasil().textContent));
  assert.strictEqual(t.sesudah.length, 0);

  // 9. gagal uji tampil sebagai galat tanpa menutup dialog
  t = jalankan();
  await t.k.buka();
  await t.tombol('+ Tambah koneksi').onclick();
  t.jawab.uji = {ok: false, error: 'Ditolak server (401): API key salah atau belum diisi'};
  await t.tombol('Uji koneksi').onclick(); await tunggu();
  assert.ok(t.hasil().className.includes('gagal') && /401/.test(t.hasil().textContent));
  assert.strictEqual(t.tirai().hidden, false);

  // 10. tombol tambah hilang bila batas koneksi tambahan tercapai
  const banyak = [];
  for (let i = 0; i < 8; i++) banyak.push(Object.assign({}, ONLINE, {id: 'k' + i, nama: 'P' + i}));
  t = jalankan(banyak);
  await t.k.buka();
  assert.strictEqual(t.tombol('+ Tambah koneksi').hidden, true);

  // 11. peringatan dari server tampil saat koneksi diubah
  t = jalankan([Object.assign({}, ONLINE, {peringatan: 'Kunci API dikirim tanpa enkripsi (http)'})]);
  await t.k.buka();
  await t.item('kabc123').children.find(c => c.className && c.className.includes('kon-item-aksi')).children[0].onclick();
  assert.ok(/tanpa enkripsi/.test(t.hasil().textContent));
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
