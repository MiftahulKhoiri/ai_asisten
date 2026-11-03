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

function jalankan(awal) {
  const panggilan = [], toasts = [], sesudah = [];
  const body = mk('body');
  const state = Object.assign({alamat: 'http://127.0.0.1:8080', jenis: 'llama', key_ada: true, sumber: 'web', peringatan: ''}, awal || {});
  const respon = (k, obj) => ({ok: k < 400, status: k, json: async () => obj});
  const jawab = {uji: {ok: true, jumlah: 3, contoh: ['a', 'b', 'c'], router: true, peringatan: ''}, simpan: null, reset: null};
  async function fetchPalsu(url, o) {
    o = o || {};
    panggilan.push({url, metode: o.method || 'GET', body: o.body ? JSON.parse(o.body) : null, auth: (o.headers || {}).Authorization});
    if (url === '/api/koneksi' && o.method !== 'POST') return respon(200, state);
    if (url === '/api/koneksi/uji') return respon(200, jawab.uji);
    if (url === '/api/koneksi') return jawab.simpan || respon(200, {ok: true, tersimpan: true, koneksi: Object.assign(state, JSON.parse(o.body).key === '' ? {key_ada: false} : {})});
    if (url === '/api/koneksi/reset') return jawab.reset || respon(200, {ok: true, koneksi: Object.assign(state, {sumber: 'lingkungan', alamat: 'http://127.0.0.1:8080'})});
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
    hasil: () => cari(body, e => /^kon-hasil/.test(e.className))};
}
const tunggu = () => new Promise(r => setTimeout(r, 5));

(async () => {
  // 1. baris ringkas memuat alamat, jenis, dan tanda key - tanpa kuncinya
  let t = jalankan();
  t.k.perbarui({alamat: 'http://pi.local:8080', jenis: 'online', key_ada: true});
  assert.strictEqual(t.wadah.children[0].textContent, 'Server model: http://pi.local:8080 · penyedia online · API key ✔');
  t.k.perbarui({alamat: 'http://127.0.0.1:8080', jenis: 'llama', key_ada: false});
  assert.strictEqual(t.wadah.children[0].textContent, 'Server model: http://127.0.0.1:8080 · llama-server');

  // 2. buka: mengambil pengaturan terbaru, mengisi alamat, kolom key kosong, dialog tampil
  t = jalankan();
  await t.k.buka();
  assert.strictEqual(t.panggilan[0].url, '/api/koneksi');
  assert.strictEqual(t.panggilan[0].auth, 'Bearer TOK');
  assert.strictEqual(t.el('konAlamat').value, 'http://127.0.0.1:8080');
  assert.strictEqual(t.el('konKunci').value, '');
  assert.strictEqual(t.el('konKunci').type, 'password');
  assert.ok(/tersimpan/.test(t.el('konKunci').placeholder));
  assert.strictEqual(t.tirai().hidden, false);
  assert.strictEqual(t.tombol('Pakai bawaan').hidden, false);     // sumber 'web'

  // 3. uji tanpa mengetik key: kolom key tidak dikirim (server memakai yang tersimpan)
  await t.tombol('Uji koneksi').onclick(); await tunggu();
  let uji = t.panggilan.find(p => p.url === '/api/koneksi/uji');
  assert.deepStrictEqual(uji.body, {alamat: 'http://127.0.0.1:8080', jenis: 'llama'});
  assert.ok(/Terhubung · 3 model/.test(t.hasil().textContent), t.hasil().textContent);
  assert.ok(/Mode router/.test(t.hasil().textContent));
  assert.ok(t.hasil().className.includes('ok'));

  // 4. uji dengan key baru dan jenis online; server tanpa router
  t.el('konAlamat').value = ' https://api.contoh.com/v1 ';
  t.el('konKunci').value = ' sk-baru ';
  t.el('konKunci').handlers.input();
  t.dlg().children.find(c => c.className && c.className.includes('kon-seg')).children[1].onclick();
  t.jawab.uji = {ok: true, jumlah: 40, contoh: ['x'], router: false, peringatan: ''};
  await t.tombol('Uji koneksi').onclick(); await tunggu();
  uji = t.panggilan.filter(p => p.url === '/api/koneksi/uji').pop();
  assert.deepStrictEqual(uji.body, {alamat: 'https://api.contoh.com/v1', jenis: 'online', key: 'sk-baru'});
  assert.ok(/Tanpa mode router/.test(t.hasil().textContent));

  // 5. uji gagal tampil sebagai galat, tanpa menutup dialog
  t.jawab.uji = {ok: false, error: 'Ditolak server (401): API key salah atau belum diisi'};
  await t.tombol('Uji koneksi').onclick(); await tunggu();
  assert.ok(t.hasil().className.includes('gagal'));
  assert.ok(/401/.test(t.hasil().textContent));
  assert.strictEqual(t.tirai().hidden, false);

  // 6. simpan: dikirim, kolom key dikosongkan, dialog ditutup, ringkasan diperbarui, setelahUbah dipanggil
  await t.tombol('Simpan').onclick(); await tunggu();
  const simpan = t.panggilan.filter(p => p.url === '/api/koneksi' && p.metode === 'POST').pop();
  assert.strictEqual(simpan.body.key, 'sk-baru');
  assert.strictEqual(t.el('konKunci').value, '');
  assert.strictEqual(t.tirai().hidden, true);
  assert.strictEqual(t.sesudah.length, 1);
  assert.ok(t.toasts.includes('Koneksi disimpan'));

  // 7. hapus key tersimpan: dikirim key kosong
  t = jalankan();
  await t.k.buka();
  t.tombol('Hapus API key tersimpan').onclick();
  assert.ok(/dihapus saat Simpan/.test(cari(t.body, e => /kon-kunci-ket/.test(e.className)).textContent));
  await t.tombol('Simpan').onclick(); await tunggu();
  const hapus = t.panggilan.filter(p => p.url === '/api/koneksi' && p.metode === 'POST').pop();
  assert.strictEqual(hapus.body.key, '');

  // 8. simpan ditolak server (mis. ada proses berjalan): pesan tampil, dialog tetap terbuka
  t = jalankan();
  await t.k.buka();
  t.jawab.simpan = respon409();
  await t.tombol('Simpan').onclick(); await tunggu();
  assert.ok(/Sedang ada proses/.test(t.hasil().textContent));
  assert.strictEqual(t.tirai().hidden, false);
  assert.strictEqual(t.sesudah.length, 0);

  // 9. pakai bawaan: hanya terlihat bila pengaturan berasal dari web; memanggil reset
  t = jalankan({sumber: 'bawaan'});
  await t.k.buka();
  assert.strictEqual(t.tombol('Pakai bawaan').hidden, true);
  t = jalankan();
  await t.k.buka();
  await t.tombol('Pakai bawaan').onclick(); await tunggu();
  assert.ok(t.panggilan.some(p => p.url === '/api/koneksi/reset' && p.metode === 'POST'));
  assert.strictEqual(t.sesudah.length, 1);

  // 10. peringatan dari server tampil saat dialog dibuka
  t = jalankan({peringatan: 'Kunci API dikirim tanpa enkripsi (http)'});
  await t.k.buka();
  assert.ok(/tanpa enkripsi/.test(t.hasil().textContent));

  // 11. kunci tidak pernah ditulis ke teks ringkasan atau toast
  t = jalankan();
  await t.k.buka();
  t.el('konKunci').value = 'RAHASIA-XYZ'; t.el('konKunci').handlers.input();
  await t.tombol('Simpan').onclick(); await tunggu();
  assert.ok(!t.wadah.textContent.includes('RAHASIA-XYZ'));
  assert.ok(!t.toasts.join(' ').includes('RAHASIA-XYZ'));
  console.log('OK');

  function respon409() { return {ok: false, status: 409, json: async () => ({ok: false, error: 'Sedang ada proses berjalan. Tunggu selesai atau hentikan dulu.'})}; }
})().catch(e => { console.error(e); process.exit(1); });
