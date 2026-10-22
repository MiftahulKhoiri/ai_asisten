// Tes asap web/unggah.js dengan DOM dan fetch tiruan (butuh node). Dipakai oleh tests/test_unggah.py.
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
// objek dari konteks vm punya prototipe berbeda: bandingkan lewat JSON
assert.same = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);

function El(tag) {
  return {
    tag, className: '', textContent: '', hidden: false, children: [], attrs: {}, parentNode: null,
    title: '', type: '', multiple: false, value: '', files: [], onclick: null, onchange: null,
    get firstChild() { return this.children[0] || null; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    append(...cs) { cs.forEach(c => this.appendChild(c)); },
    insertBefore(n, ref) {
      n.parentNode = this; const i = ref ? this.children.indexOf(ref) : this.children.length;
      this.children.splice(i < 0 ? this.children.length : i, 0, n); return n;
    },
    setAttribute(k, v) { this.attrs[k] = v; },
    click() { if (this.onclick) this.onclick(); },
    set innerHTML(v) { this.children = []; }, get innerHTML() { return ''; },
  };
}
function semuaTeks(e) { return [e.textContent].concat(e.children.map(semuaTeks)).join('|'); }
function cari(e, kelas) {
  const h = []; (function jalan(x) { if ((' ' + x.className + ' ').includes(' ' + kelas + ' ')) h.push(x); x.children.forEach(jalan); })(e); return h;
}

const lemari = {}, simpan = {
  getItem: k => (k in lemari ? lemari[k] : null), setItem: (k, v) => { lemari[k] = String(v); }, removeItem: k => { delete lemari[k]; }};
const panggilan = [];
let skenario = 'normal';
async function fetchPalsu(url, opsi) {
  opsi = opsi || {};
  panggilan.push({url, metode: opsi.method || 'GET', header: opsi.headers || {}, body: opsi.body});
  const balas = (kode, obj) => ({ok: kode < 400, status: kode, json: async () => obj});
  if (url === '/api/unggah/hapus') {
    const b = JSON.parse(opsi.body);
    return balas(200, {ok: true, berkas: b.nama ? [{nama: 'b.py', ukuran: 5}] : []});
  }
  if (url.startsWith('/api/unggah?paket=') && !opsi.method) {
    return url.endsWith('=lama') ? balas(200, {paket: 'lama', berkas: [{nama: 'sisa.py', ukuran: 9}]}) : balas(404, {error: 'tidak ada'});
  }
  if (opsi.method === 'POST') {
    const nama = decodeURIComponent(opsi.headers['X-Nama']);
    if (skenario === 'kedaluwarsa' && url.includes('paket=lama')) return balas(404, {error: 'Paket unggahan tidak ditemukan'});
    if (nama === 'salah.zip') return balas(400, {error: 'bukan berkas zip yang valid'});
    if (nama === 'proyek.zip') {
      return balas(200, {paket: 'p1', baru: ['b.py'], dilewati: [{nama: 'x.png', alasan: 'jenis berkas tidak didukung'}], diabaikan: 2,
        berkas: [{nama: 'a.py', ukuran: 11}, {nama: 'b.py', ukuran: 5}]});
    }
    return balas(200, {paket: 'p1', baru: [nama], dilewati: [], berkas: [{nama, ukuran: 11}]});
  }
  return balas(404, {});
}

const container = El('section'), form = El('form'); container.appendChild(form);
const info = [];
const konteks = {window: {sessionStorage: simpan}, document: {createElement: El}, fetch: fetchPalsu, console};
vm.createContext(konteks);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'web', 'unggah.js'), 'utf8'), konteks);
assert.ok(konteks.window.Unggah, 'window.Unggah tidak terpasang');

(async () => {
  const tunggu = ms => new Promise(r => setTimeout(r, ms));
  const u = konteks.window.Unggah.pasang({form, token: () => 'T0K', kunci: 'k_uji', info: (t, g) => info.push([t, !!g])});
  const bar = container.children[0], tombol = form.children[0], pilih = form.children[form.children.length - 1];
  assert.strictEqual(bar.className, 'lampiran-bar');
  assert.ok(bar.hidden, 'bar kosong harus tersembunyi');
  assert.strictEqual(tombol.type, 'button');                                    // tidak ikut submit form
  assert.strictEqual(pilih.type, 'file'); assert.ok(pilih.multiple);
  assert.strictEqual(u.paket(), null); assert.same(u.nama(), []);

  // 1. satu berkas: paket baru dibuat server, header benar, chip tampil
  pilih.files = [{name: 'a.py'}]; pilih.onchange(); assert.ok(u.sibuk(), 'harus sibuk saat mengunggah');
  assert.ok(semuaTeks(bar).includes('⏳ a.py'));
  await tunggu(30);
  assert.ok(!u.sibuk());
  assert.strictEqual(panggilan[0].url, '/api/unggah');
  assert.strictEqual(panggilan[0].header['Authorization'], 'Bearer T0K');
  assert.strictEqual(panggilan[0].header['X-Nama'], 'a.py');
  assert.strictEqual(u.paket(), 'p1'); assert.same(u.nama(), ['a.py']);
  assert.ok(!bar.hidden && semuaTeks(bar).includes('a.py') && semuaTeks(bar).includes('11 B'));
  assert.strictEqual(lemari['k_uji'], 'p1');                                    // paket diingat untuk reload

  // 2. zip ke paket yang sama, dengan berkas yang dilewati dan nama berspasi di-encode
  pilih.files = [{name: 'proyek.zip'}]; pilih.onchange(); await tunggu(30);
  assert.strictEqual(panggilan[1].url, '/api/unggah?paket=p1');
  assert.same(u.nama(), ['a.py', 'b.py']);
  const teks = semuaTeks(bar);
  assert.ok(teks.includes('1 berkas dilewati: x.png (jenis berkas tidak didukung)'), teks);
  assert.ok(teks.includes('2 entri zip diabaikan'), teks);
  assert.ok(teks.includes('Hapus semua'));

  // 3. hapus satu berkas lewat tombol ✕ pada chip
  const chip = cari(bar, 'chip')[0], x = chip.children[chip.children.length - 1];
  assert.strictEqual(x.attrs['aria-label'], 'Hapus a.py');
  x.onclick(); await tunggu(30);
  const hapus = panggilan[panggilan.length - 1];
  assert.strictEqual(hapus.url, '/api/unggah/hapus');
  assert.same(JSON.parse(hapus.body), {paket: 'p1', nama: 'a.py'});
  assert.same(u.nama(), ['b.py']);

  // 4. galat dari server dilaporkan lewat info dan tidak merusak daftar
  pilih.files = [{name: 'salah.zip'}]; pilih.onchange(); await tunggu(30);
  assert.ok(info.some(([t, g]) => g && t.includes('salah.zip') && t.includes('bukan berkas zip')), JSON.stringify(info));
  assert.same(u.nama(), ['b.py']);

  // 5. berkas dipakai server (kirim berhasil): lepas melupakan paket tanpa menghapus di server
  const n = panggilan.length; u.lepas();
  assert.strictEqual(u.paket(), null); assert.ok(bar.hidden); assert.strictEqual(lemari['k_uji'], undefined);
  assert.strictEqual(panggilan.length, n);

  // 6. bersihkan: hapus paket di server
  pilih.files = [{name: 'c.py'}]; pilih.onchange(); await tunggu(30);
  await u.bersihkan(); await tunggu(10);
  assert.strictEqual(JSON.parse(panggilan[panggilan.length - 1].body).paket, 'p1');
  assert.strictEqual(u.paket(), null);

  // 7. paket kedaluwarsa di server: unggahan diulang ke paket baru, tanpa galat
  lemari['k_uji'] = 'basi'; skenario = 'kedaluwarsa';
  const form2 = El('form'), wadah2 = El('section'); wadah2.appendChild(form2);
  const u2 = konteks.window.Unggah.pasang({form: form2, token: () => 'T0K', kunci: 'k_uji', info: (t, g) => info.push([t, !!g])});
  await tunggu(30);
  assert.strictEqual(lemari['k_uji'], undefined, 'paket basi harus dilupakan saat reload');
  assert.strictEqual(u2.paket(), null);

  // 8. pulihkan paket yang masih ada setelah halaman dimuat ulang
  lemari['k_uji'] = 'lama';
  const form3 = El('form'), wadah3 = El('section'); wadah3.appendChild(form3);
  const u3 = konteks.window.Unggah.pasang({form: form3, token: () => 'T0K', kunci: 'k_uji', info() {}});
  await tunggu(30);
  assert.strictEqual(u3.paket(), 'lama'); assert.same(u3.nama(), ['sisa.py']);
  assert.ok(!wadah3.children[0].hidden);
  // 9. paket kedaluwarsa saat mengunggah: diulang ke paket baru tanpa galat
  skenario = 'kedaluwarsa'; const awal = panggilan.length;
  const ib = info.length;
  const pilih3 = form3.children[form3.children.length - 1];
  pilih3.files = [{name: 'd.py'}]; pilih3.onchange(); await tunggu(40);
  assert.strictEqual(panggilan[awal].url, '/api/unggah?paket=lama');
  assert.strictEqual(panggilan[awal + 1].url, '/api/unggah');                  // diulang tanpa paket basi
  assert.strictEqual(u3.paket(), 'p1'); assert.same(u3.nama(), ['d.py']);
  assert.strictEqual(info.length, ib, 'tidak boleh ada galat yang tampil');
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
