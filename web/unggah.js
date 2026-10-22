/* unggah.js - tombol 📎 dan daftar lampiran, dipakai halaman chat dan Agent.
 *
 *   const u = Unggah.pasang({form, token: () => TOKEN, kunci: 'aa_paket_chat', info: (teks, galat) => ...});
 *   u.paket()    id paket di server (atau null)       u.nama()    nama berkas yang sudah terunggah
 *   u.sibuk()    true selama masih mengunggah          u.lepas()   lupakan paket (sudah dipakai server)
 *   u.bersihkan()  hapus paket di server dan di halaman
 *
 * Berkas teks/kode dan zip dikirim satu per satu sebagai byte mentah ke /api/unggah. Server memeriksa
 * jenis, ukuran, dan jalur berkas; yang ditolak dilaporkan lewat `info`.
 */
(function () {
  'use strict';
  function el(tag, cls, teks) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (teks !== undefined) e.textContent = teks;
    return e;
  }
  function ukuranTeks(n) { return n >= 10000 ? Math.round(n / 1000) + ' KB' : n >= 1000 ? (n / 1000).toFixed(1) + ' KB' : n + ' B'; }

  function pasang(opt) {
    const form = opt.form, kunci = opt.kunci || 'aa_paket';
    const info = opt.info || function () {};
    const st = {paket: null, berkas: [], proses: [], catatan: ''};
    const lemari = window.sessionStorage;

    const bar = el('div', 'lampiran-bar'); bar.hidden = true;
    form.parentNode.insertBefore(bar, form);
    const tombol = el('button', 'btn abu lampir', '📎'); tombol.type = 'button';
    tombol.setAttribute('aria-label', 'Lampirkan berkas'); tombol.title = 'Lampirkan berkas atau zip';
    const pilih = el('input'); pilih.type = 'file'; pilih.multiple = true; pilih.hidden = true;
    form.insertBefore(tombol, form.firstChild); form.appendChild(pilih);

    function simpan() {
      try { if (st.paket) lemari.setItem(kunci, st.paket); else lemari.removeItem(kunci); } catch (e) { /* abaikan */ }
    }
    function gambar() {
      bar.innerHTML = '';
      for (const b of st.berkas) {
        const c = el('span', 'chip'), n = el('span', 'nm', b.nama);
        n.title = b.nama; c.append(n, el('small', '', ukuranTeks(b.ukuran)));
        const x = el('button', '', '✕'); x.type = 'button'; x.setAttribute('aria-label', 'Hapus ' + b.nama);
        x.onclick = () => hapusSatu(b.nama); c.appendChild(x); bar.appendChild(c);
      }
      for (const nama of st.proses) bar.appendChild(el('span', 'chip proses', '⏳ ' + nama));
      if (st.berkas.length > 1) {
        const s = el('button', 'semua', 'Hapus semua'); s.type = 'button'; s.onclick = () => bersihkan(); bar.appendChild(s);
      }
      if (st.catatan) bar.appendChild(el('div', 'catatan', st.catatan));
      bar.hidden = !(st.berkas.length || st.proses.length || st.catatan);
    }
    async function panggil(path, opsi) {
      opsi = Object.assign({}, opsi || {});
      opsi.headers = Object.assign({'Authorization': 'Bearer ' + opt.token()}, opsi.headers || {});
      return fetch(path, opsi);
    }
    function terima(j) {
      st.paket = j.paket || null; st.berkas = j.berkas || []; simpan();
    }
    function laporkan(j) {
      const lewat = j.dilewati || [], lain = j.lainnya || 0, abai = j.diabaikan || 0;
      const teks = [];
      if (lewat.length || lain) {
        teks.push((lewat.length + lain) + ' berkas dilewati: ' + lewat.slice(0, 3).map(x => x.nama + ' (' + x.alasan + ')').join('; ')
          + (lewat.length > 3 || lain ? ' ...' : ''));
      }
      if (abai) teks.push(abai + ' entri zip diabaikan (.git, __pycache__, dll.)');
      st.catatan = teks.join(' · ');
    }
    async function unggahSatu(file, ulang) {
      const nama = file.webkitRelativePath || file.name;
      const r = await panggil('/api/unggah' + (st.paket ? '?paket=' + st.paket : ''), {
        method: 'POST', body: file,
        headers: {'X-Nama': encodeURIComponent(nama), 'Content-Type': 'application/octet-stream'}});
      if (r.status === 401) throw new Error('Token salah.');
      const j = await r.json().catch(() => ({}));
      if (r.status === 404 && st.paket && !ulang) {       // paket kedaluwarsa di server: mulai paket baru
        st.paket = null; st.berkas = []; simpan(); return unggahSatu(file, true);
      }
      if (!r.ok) throw new Error(nama + ': ' + (j.error || ('HTTP ' + r.status)));
      terima(j); laporkan(j);
    }
    let antrian = Promise.resolve();
    function tambah(files) {
      for (const f of files) {
        st.proses.push(f.name); gambar();
        antrian = antrian.then(async () => {
          try { await unggahSatu(f); }
          catch (e) {
            info('⚠ ' + (e.name === 'TypeError' ? f.name + ': gagal mengunggah (koneksi terputus atau berkas terlalu besar).' : e.message), true);
          }
          finally { const i = st.proses.indexOf(f.name); if (i >= 0) st.proses.splice(i, 1); gambar(); }
        });
      }
    }
    async function hapusSatu(nama) {
      try {
        const r = await panggil('/api/unggah/hapus', {method: 'POST', body: JSON.stringify({paket: st.paket, nama}),
          headers: {'Content-Type': 'application/json'}});
        const j = await r.json().catch(() => ({}));
        if (r.ok) { st.berkas = j.berkas || []; if (!st.berkas.length) st.paket = null; simpan(); st.catatan = ''; gambar(); }
      } catch (e) { info('⚠ ' + e.message, true); }
    }
    async function bersihkan() {
      const paket = st.paket;
      lepas();
      if (!paket) return;
      try { await panggil('/api/unggah/hapus', {method: 'POST', body: JSON.stringify({paket}),
        headers: {'Content-Type': 'application/json'}}); } catch (e) { /* abaikan */ }
    }
    function lepas() { st.paket = null; st.berkas = []; st.catatan = ''; simpan(); gambar(); }

    tombol.onclick = () => pilih.click();
    pilih.onchange = () => { const f = Array.from(pilih.files || []); pilih.value = ''; if (f.length) tambah(f); };

    // pulihkan paket yang belum terpakai setelah halaman dimuat ulang
    let tersimpan = null;
    try { tersimpan = lemari.getItem(kunci); } catch (e) { /* abaikan */ }
    if (tersimpan) {
      panggil('/api/unggah?paket=' + encodeURIComponent(tersimpan)).then(async r => {
        if (!r.ok) { try { lemari.removeItem(kunci); } catch (e) { /* abaikan */ } return; }
        const j = await r.json(); st.paket = j.paket; st.berkas = j.berkas || []; gambar();
      }).catch(() => {});
    }

    return {
      paket: () => (st.berkas.length ? st.paket : null),
      nama: () => st.berkas.map(b => b.nama),
      sibuk: () => st.proses.length > 0,
      lepas, bersihkan,
    };
  }
  window.Unggah = {pasang};
})();
