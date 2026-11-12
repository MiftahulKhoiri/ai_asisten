/* beranda.js - logika Beranda aplikasi Android.
   Pekerjaan jaringan (tes koneksi, cek dan pasang pembaruan) dikerjakan Java lewat jembatan
   window.AiAsistenApp; hasilnya dikirim balik ke fungsi window.Beranda.* di bawah. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const App = window.AiAsistenApp;
  let aktif = false;
  let toastT = null;

  function salam() {   // sama dengan dasbor.js
    const j = new Date().getHours();
    return j < 4 ? 'Selamat malam' : j < 11 ? 'Selamat pagi' : j < 15 ? 'Selamat siang' : j < 19 ? 'Selamat sore' : 'Selamat malam';
  }
  function toast(m) {
    const t = $('toast'); t.textContent = m; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 3200);
  }
  function status(id, st, teks) {
    const el = $(id); el.dataset.st = st || '';
    el.querySelector('span').textContent = teks;
  }
  function tanpaSkema(a) { return a.replace(/^https?:\/\//, ''); }

  function setAktif(ok, alamatDasar) {
    aktif = ok;
    $('btnMasuk').hidden = !ok;
    if (ok) status('chipServer', 'ok', 'Server aktif');
    else if (alamatDasar === null) status('chipServer', '', 'Belum terhubung');
  }

  /* ---------- server ---------- */
  function tes() {
    const v = $('alamat').value.trim();
    $('alamat').blur();
    setAktif(false);
    if (!App) { status('stTes', 'mati', 'Jembatan aplikasi tidak tersedia'); return; }
    $('btnTes').disabled = true;
    status('stTes', 'muat', 'Mengetes...');
    status('chipServer', 'muat', 'Menghubungkan...');
    App.tes(v);
  }

  function gambarRiwayat(daftar) {
    const ul = $('riwayat'); ul.textContent = '';
    $('kartuRiwayat').hidden = !daftar.length;
    for (const a of daftar) {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'alamat';
      b.innerHTML = '<span class="rt"><b></b><small>Ketuk untuk mengetes</small></span>';
      b.querySelector('b').textContent = tanpaSkema(a);
      b.onclick = () => { $('alamat').value = a; tes(); };
      const x = document.createElement('button');
      x.type = 'button'; x.className = 'hapus'; x.textContent = '✕';
      x.setAttribute('aria-label', 'Hapus ' + tanpaSkema(a));
      x.onclick = () => { if (App) gambarRiwayat(JSON.parse(App.hapusRiwayat(a))); };
      li.appendChild(b); li.appendChild(x); ul.appendChild(li);
    }
  }

  /* ---------- pembaruan ---------- */
  let aksiApp = 'cek';   // 'cek' | 'pasang' | 'sibuk'
  function setAksiApp(aksi, teks) {
    aksiApp = aksi;
    $('btnAppTeks').textContent = teks;
    $('btnApp').disabled = aksi === 'sibuk';
  }
  function cekPembaruan() {
    if (!App) return;
    setAksiApp('sibuk', 'Memeriksa...');
    status('stApp', 'muat', 'Memeriksa pembaruan...');
    App.cekPembaruan();
  }

  /* ---------- dipanggil dari Java ---------- */
  window.Beranda = {
    hasilTes(json) {
      const h = JSON.parse(json);
      $('btnTes').disabled = false;
      if (h.batal) return;               // hasil tes lama, alamat sudah diganti
      status('stTes', h.st, h.pesan);
      setAktif(h.aktif, h.aktif ? h.dasar : null);
      if (!h.aktif) status('chipServer', h.st === 'mati' ? 'mati' : 'peringatan', h.st === 'mati' ? 'Server tidak aktif' : 'Bukan server AI Asisten');
      if (h.riwayat) gambarRiwayat(h.riwayat);
    },
    putus(pesan) {                       // koneksi halaman web terputus -> kembali ke sini
      setAktif(false);
      status('stTes', 'mati', pesan);
      status('chipServer', 'mati', 'Koneksi terputus');
    },
    hasilPembaruan(json) {
      const h = JSON.parse(json);
      if (h.galat) { status('stApp', 'peringatan', 'Tidak bisa memeriksa: ' + h.galat); setAksiApp('cek', 'Periksa lagi'); }
      else if (h.ada) {
        status('stApp', 'ok', 'Pembaruan tersedia: versi ' + h.versi + ' · build ' + h.build + (h.kb ? ' (' + h.kb + ' KB)' : ''));
        setAksiApp('pasang', 'Unduh dan pasang versi ' + h.versi);
      } else { status('stApp', '', h.kosong ? 'Belum ada rilis di GitHub' : 'Sudah versi terbaru'); setAksiApp('cek', 'Periksa pembaruan'); }
    },
    kemajuan(dapat, total) {
      const b = $('bilah'); b.hidden = false;
      if (total > 0) b.value = Math.round(dapat * 1000 / total);
      status('stApp', 'muat', 'Mengunduh ' + Math.round(dapat / 1024) + (total > 0 ? ' dari ' + Math.round(total / 1024) : '') + ' KB');
    },
    hasilPasang(json) {
      const h = JSON.parse(json);
      $('bilah').hidden = true;
      status('stApp', h.st, h.pesan);
      if (h.st === 'muat') setAksiApp('sibuk', 'Menunggu konfirmasi...');
      else if (h.st === 'ok') setAksiApp('cek', 'Periksa pembaruan');
      else setAksiApp('pasang', 'Coba pasang lagi');
    },
  };

  /* ---------- awal ---------- */
  $('salam').textContent = salam();
  $('btnTes').onclick = tes;
  $('alamat').addEventListener('keydown', e => { if (e.key === 'Enter') tes(); });
  $('alamat').addEventListener('input', () => {
    if (aktif || $('stTes').dataset.st) { setAktif(false, null); status('stTes', '', 'Belum dites'); }
    if (App) App.batalTes();
  });
  $('btnMasuk').onclick = () => { if (aktif && App) App.masuk(); };
  $('btnApp').onclick = () => {
    if (!App) return;
    if (aksiApp === 'pasang') { setAksiApp('sibuk', 'Mengunduh...'); App.pasang(); }
    else if (aksiApp === 'cek') cekPembaruan();
  };
  $('btnRilis').onclick = () => { if (App) App.bukaRilis(); };
  $('btnKeluar').onclick = () => { if (App) App.keluar(); };

  if (!App) { toast('Halaman ini hanya berfungsi di aplikasi Android.'); return; }
  const info = JSON.parse(App.info());
  $('teksVersi').textContent = 'Versi ' + info.versi + ' · build ' + info.build + '. Pembaruan diambil dari GitHub Releases.';
  $('alamat').value = info.alamat || '';
  gambarRiwayat(info.riwayat || []);
  if (info.alamat) tes(); else status('stTes', '', 'Isi alamat lalu tekan Tes koneksi');
  cekPembaruan();
})();
