// Tes asap web/serahkan.js dengan DOM dan fetch tiruan (butuh node). Dipakai oleh tests/test_serahterima.py.
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
assert.same = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);   // lintas konteks vm

function El(tag) {
  return {
    tag, className: '', textContent: '', hidden: false, disabled: false, children: [], attrs: {}, parentNode: null,
    title: '', type: '', value: '', href: '', id: '', checked: false, onclick: null,
    get firstChild() { return this.children[0] || null; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    append(...cs) { cs.forEach(c => this.appendChild(c)); },
    insertBefore(n, ref) { n.parentNode = this; const i = ref ? this.children.indexOf(ref) : this.children.length; this.children.splice(i < 0 ? this.children.length : i, 0, n); return n; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; },
    remove() { if (this.parentNode) this.parentNode.removeChild(this); },
    setAttribute(k, v) { this.attrs[k] = v; }, click() { if (this.onclick) this.onclick(); },
  };
}
function teks(e) { return [e.textContent].concat(e.children.map(teks)).join('|'); }
function cari(e, kelas) { const h = []; (function j(x) { if ((' ' + x.className + ' ').includes(' ' + kelas + ' ')) h.push(x); x.children.forEach(j); })(e); return h; }
function semuaTombol(e) { const h = []; (function j(x) { if (x.tag === 'button' || x.tag === 'a') h.push(x); x.children.forEach(j); })(e); return h; }

const BRIEF = {ringkasan: 'Tujuan: kalkulator.\nYang diminta: tambah.', otomatis: true, lampiran: [{nama: 'a.py', ukuran: 11}],
  jalur: 'buat', jalur_label: 'Buat / kembangkan', alasan: 'tidak ada tanda perbaikan', lanjut: {run: '20261001-000000-aaaa', judul: 'Proses lama', status: 'lolos'}};
const EVENTS = [
  {t: 'mulai', id: '20261024-120000-bbbb'}, {t: 'jalur', jalur: 'buat', label: 'Buat / kembangkan', urut: [{kunci: 'rencana'}, {kunci: 'tulis'}, {kunci: 'periksa'}, {kunci: 'jelaskan'}]},
  {t: 'tahap', tahap: 'rencana', peran: 'Perencana'}, {t: 'tahap', tahap: 'tulis', peran: 'Pelaksana'}, {t: 'putaran', n: 1, maks: 3},
  {t: 'tahap', tahap: 'periksa', peran: 'Pemeriksa'}, {t: 'tahap', tahap: 'jelaskan', peran: 'Penjelas'}, {t: 'selesai', status: 'lolos'}];
const panggilan = [], lemari = {ag_cfg: JSON.stringify({mode: 2, p: 'A', e: 'B', maks: 3, bongkar: true, izinUji: false})};
let skenario = 'normal', polling = 0, unduhan = [];
async function fetchPalsu(url, opsi) {
  opsi = opsi || {}; panggilan.push({url, metode: opsi.method || 'GET', header: opsi.headers || {}, body: opsi.body});
  const balas = (kode, obj) => ({ok: kode < 400, status: kode, json: async () => obj, blob: async () => ({ukuran: 3})});
  if (url === '/api/handoff/ringkas') return skenario === 'gagal_ringkas' ? balas(409, {error: 'Model belum dimuat. Pilih model dulu.'}) : balas(200, BRIEF);
  if (url === '/api/handoff/kirim') return skenario === 'gagal_kirim' ? balas(409, {error: 'Masih ada proses berjalan'}) : balas(200, {ok: true, sesi: 's1'});
  if (url === '/api/stop') return balas(200, {ok: true});
  if (url.startsWith('/api/agent/event?')) {
    polling++;
    if (skenario === 'putus' && polling === 2) throw new TypeError('Failed to fetch');
    const dari = Number(new URL('http://x' + url).searchParams.get('dari')), akhir = Math.min(EVENTS.length, dari + 3);
    return balas(200, {events: EVENTS.slice(dari, akhir), next: akhir, habis: akhir >= EVENTS.length, aktif: akhir < EVENTS.length});
  }
  if (url.startsWith('/api/agent/run/')) { unduhan.push(url); return balas(200, {}); }
  return balas(404, {});
}
const body = El('body'), header = El('header'), btnAgent = El('a'), wadah = El('div');
header.appendChild(btnAgent);
const info = [], toastPesan = []; let muatUlang = 0, selesai = 0, chatId = '20261024-110000-cccc';
const konteks = {window: {localStorage: {getItem: k => (k in lemari ? lemari[k] : null)}, SERAHKAN_JEDA_ULANG: 5},
  document: {createElement: El, body}, URL: {createObjectURL: () => 'blob:x', revokeObjectURL() {}}, fetch: fetchPalsu, console, setTimeout, new_URL: null};
konteks.URL = Object.assign(function (u) { return new (require('url').URL)(u); }, {createObjectURL: () => 'blob:x', revokeObjectURL() {}});
vm.createContext(konteks);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'web', 'serahkan.js'), 'utf8'), konteks);
const S = konteks.window.Serahkan; assert.ok(S, 'window.Serahkan tidak terpasang');
const tunggu = ms => new Promise(r => setTimeout(r, ms));
function baru() {
  wadah.children = []; muatUlang = 0; selesai = 0;
  return S.pasang({token: () => 'T0K', chatId: () => chatId, wadah, sebelum: btnAgent, gulir() {},
    info: (t, g) => info.push([t, !!g]), toast: t => toastPesan.push(t), sibuk: () => false,
    muatUlang: async () => { muatUlang++; }, setelahSelesai: () => { selesai++; }});
}

(async () => {
  // --- konfigurasi Agent dibaca dari penyimpanan yang sama dengan halaman Agent
  assert.same(S.bacaCfg(konteks.window.localStorage), {mode: 2, model_p: 'A', model_e: 'B', model_c: 'A', maks: 3, bongkar: true, uji: false});
  assert.strictEqual(S.bacaCfg({getItem: () => null}), null, 'tanpa pengaturan: null');
  assert.strictEqual(S.bacaCfg({getItem: () => JSON.stringify({mode: 3, p: 'A', e: 'B'})}), null, 'mode 3 butuh model ketiga');
  assert.strictEqual(S.bacaCfg({getItem: () => '{rusak'}), null);

  // --- tombol 🏭 di header, tersembunyi sampai layar chat
  let s = baru(); const tombol = header.children[0];
  assert.strictEqual(tombol.id, 'btnSerah'); assert.ok(tombol.hidden); s.tampilkan(true); assert.ok(!tombol.hidden);

  // --- 1. brief: ringkas -> kartu yang bisa diubah
  tombol.onclick(); await tunggu(20);
  assert.strictEqual(panggilan[0].url, '/api/handoff/ringkas'); assert.strictEqual(panggilan[0].header['Authorization'], 'Bearer T0K');
  assert.same(JSON.parse(panggilan[0].body), {id: chatId});
  const kartu = cari(wadah, 'brief')[0]; assert.ok(kartu, 'kartu brief tampil');
  const isi = kartu.children.find(c => c.tag === 'textarea'); assert.ok(isi.value.startsWith('Tujuan: kalkulator'));
  assert.ok(teks(kartu).includes('Otomatis akan memilih: Buat / kembangkan'));
  assert.ok(teks(kartu).includes('a.py'), 'lampiran terdaftar sebagai bahan kerja');
  assert.ok(teks(kartu).includes('Model Agent: A / B · maks 3 putaran · uji jalan: mati'));
  assert.ok(teks(kartu).includes('Lanjutkan dari hasil Agent sebelumnya (Proses lama)'));

  // --- 2. setujui: isi brief + pilihan jalur + model dikirim, lalu progres dipantau sampai selesai
  isi.value = 'Tujuan: kalkulator.\nYang diminta: tambah dan kurang.';
  const jalur = cari(kartu, 'jalur')[0]; const pilihPerbaiki = jalur.children.find(b => b.textContent === 'Perbaiki'); pilihPerbaiki.onclick();
  assert.strictEqual(pilihPerbaiki.attrs['aria-checked'], 'true');
  const setuju = semuaTombol(kartu).find(b => b.textContent.startsWith('Setujui'));
  setuju.onclick(); await tunggu(80);
  const kirim = panggilan.find(p => p.url === '/api/handoff/kirim'); const b = JSON.parse(kirim.body);
  assert.strictEqual(b.id, chatId); assert.strictEqual(b.tugas, 'Tujuan: kalkulator.\nYang diminta: tambah dan kurang.');
  assert.strictEqual(b.jalur, 'perbaiki'); assert.strictEqual(b.model_p, 'A'); assert.strictEqual(b.model_e, 'B'); assert.strictEqual(b.maks, 3);
  assert.strictEqual(b.uji, false); assert.strictEqual(b.muat_ulang, true); assert.strictEqual(b.lanjut, '20261001-000000-aaaa');
  const polls = panggilan.filter(p => p.url.startsWith('/api/agent/event?'));
  assert.ok(polls.length >= 3, 'dipantau lewat beberapa long-poll'); assert.ok(polls[0].url.includes('sesi=s1&dari=0'));
  assert.ok(muatUlang >= 2, 'obrolan dimuat ulang: setelah diserahkan dan setelah selesai'); assert.strictEqual(selesai, 1);
  assert.strictEqual(cari(wadah, 'serah').length, 0, 'kartu progres hilang setelah selesai'); assert.ok(!s.aktif());

  // --- tanpa menyetujui lanjutan: kotak centang dimatikan, tidak ada 'lanjut' di permintaan
  s = baru(); panggilan.length = 0; skenario = 'normal'; header.children[0].onclick(); await tunggu(20);
  const k2 = cari(wadah, 'brief')[0]; const cek = cari(k2, 'cek')[0].children[0]; cek.checked = false;
  semuaTombol(k2).find(b => b.textContent.startsWith('Setujui')).onclick(); await tunggu(80);
  assert.ok(!('lanjut' in JSON.parse(panggilan.find(p => p.url === '/api/handoff/kirim').body)));

  // --- batal, galat ringkas, galat kirim (kartu tetap ada supaya bisa dicoba lagi)
  s = baru(); header.children[0].onclick(); await tunggu(20);
  semuaTombol(cari(wadah, 'brief')[0]).find(b => b.textContent === 'Batal').onclick();
  assert.strictEqual(cari(wadah, 'serah').length, 0);
  skenario = 'gagal_ringkas'; info.length = 0; header.children[0].onclick(); await tunggu(20);
  assert.strictEqual(cari(wadah, 'serah').length, 0); assert.ok(info.some(([t, g]) => g && t.includes('Model belum dimuat')));
  skenario = 'gagal_kirim'; header.children[0].onclick(); await tunggu(5); skenario = 'normal';
  header.children[0].onclick(); await tunggu(20);
  skenario = 'gagal_kirim'; const k3 = cari(wadah, 'brief')[0];
  semuaTombol(k3).find(b => b.textContent.startsWith('Setujui')).onclick(); await tunggu(30);
  const galat = cari(k3, 'galat')[0]; assert.ok(!galat.hidden && galat.textContent === 'Masih ada proses berjalan');
  assert.ok(semuaTombol(k3).find(b => b.textContent.startsWith('Setujui')).disabled === false, 'bisa dicoba lagi');
  skenario = 'normal';

  // --- Model Agent belum diatur: tidak bisa dikirim
  const asli = lemari.ag_cfg; delete lemari.ag_cfg; wadah.children = []; s = baru();
  header.children[0].onclick(); await tunggu(20);
  const k4 = cari(wadah, 'brief')[0]; assert.ok(teks(k4).includes('Model Agent belum diatur'));
  assert.ok(semuaTombol(k4).find(b => b.textContent.startsWith('Setujui')).disabled);
  lemari.ag_cfg = asli;

  // --- 3. pulihkan: halaman dibuka saat Agent bekerja untuk obrolan ini; jaringan putus di tengah tidak menghentikan pemantauan
  skenario = 'putus'; polling = 0; panggilan.length = 0; wadah.children = []; s = baru();
  s.pulihkan({aktif: true, sesi: 's9', chat_id: 'obrolan-lain'}); await tunggu(20);
  assert.strictEqual(panggilan.length, 0, 'obrolan lain: tidak ikut memantau');
  s.pulihkan({aktif: true, sesi: 's9', chat_id: chatId}); await tunggu(120);
  assert.ok(panggilan.filter(p => p.url.includes('sesi=s9')).length >= 4, 'lanjut memantau setelah putus');
  const dari = panggilan.map(p => Number(new URL('http://x' + p.url).searchParams.get('dari') || 0));
  assert.same(dari, dari.slice().sort((a, b) => a - b), 'nomor event tidak mundur'); assert.strictEqual(selesai, 1);
  skenario = 'normal';

  // --- kartu hasil di obrolan: berkas bisa diunduh satu per satu atau zip
  s = baru(); const h = s.kartuHasil({run: '20261024-120000-bbbb', judul: 'Kalkulator', status: 'lolos', putaran: 2,
    berkas: [{nama: 'main.py', ukuran: 120}, {nama: 'lib/util.py', ukuran: 20}]});
  assert.ok(teks(h).includes('✔ Hasil Agent · Kalkulator') && teks(h).includes('dinyatakan jadi · 2 putaran') && teks(h).includes('main.py'));
  const tombolH = semuaTombol(h);
  unduhan.length = 0; tombolH.find(b => b.attrs['aria-label'] === 'Unduh lib/util.py').onclick(); await tunggu(20);
  assert.strictEqual(unduhan[0], '/api/agent/run/20261024-120000-bbbb/unduh?berkas=lib%2Futil.py');
  unduhan.length = 0; tombolH.find(b => b.textContent.startsWith('⬇ Unduh semua')).onclick(); await tunggu(20);
  assert.strictEqual(unduhan[0], '/api/agent/run/20261024-120000-bbbb/unduh');
  assert.strictEqual(tombolH.find(b => b.textContent === 'Lihat proses').href, 'agent.html?run=20261024-120000-bbbb');
  const analisis = s.kartuHasil({run: '20261024-120000-bbbb', judul: 'Cek', status: 'analisis', berkas: []});
  assert.ok(teks(analisis).includes('🔎 Hasil Agent') && !teks(analisis).includes('Unduh semua'));
  const info_ = s.kartuHasil({run: '20261024-120000-bbbb', judul: 'x', status: 'butuh_info', berkas: []});
  assert.ok(teks(info_).includes('serahkan lagi ke Agent'));
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
