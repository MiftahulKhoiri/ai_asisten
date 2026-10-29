/* prompt.js - pilihan prompt untuk skill Tanpa (layar "Mulai sesi" di halaman chat).
 *
 * Daftar prompt disimpan di server (prompt.json), jadi sama di semua perangkat. Setiap prompt punya
 * kotak centang: boleh memilih beberapa (digabung berurutan), tidak memilih satu pun = model berjalan
 * tanpa prompt sistem (murni). Tombol "+ prompt" membuka kolom nama, isi, dan catatan; "(✎)" mengubah
 * prompt (untuk Bawaan: membuat salinan yang bisa diubah); "(⬇)" mengunduh prompt sebagai berkas .json
 * untuk dibagikan; "⬆ Impor" memasukkan berkas .json dari orang lain; "(−)" menghapus; "Selesai"
 * menutup panel dan melanjutkan ke pilih model. Satu prompt = satu berkas di folder prompt/ server.
 *
 *   const pr = PromptPilih.pasang({token: () => TOKEN, onUbah: () => ...});
 *   pr.atur(true/false)   panel berlaku (skill Tanpa aktif) atau tidak
 *   pr.ids()  pr.nama()  pr.ringkasTeks()  pr.terbuka()  pr.aktif()
 */
(function () {
  'use strict';
  const K_PILIH = 'aa_prompt_pilih', K_SELESAI = 'aa_prompt_selesai', BAWAAN = 'bawaan';
  const $ = id => document.getElementById(id);
  function el(tag, cls, teks) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (teks !== undefined) e.textContent = teks;
    return e;
  }

  function pasang(opt) {
    const lemari = window.localStorage;
    const st = {aktif: false, daftar: [], dipilih: [], terbuka: true, dimuat: false, memuat: false, galatMuat: '', abaikan: [], info: '',
      form: {jenis: 'baru', id: null}};      // form: baru | ubah (prompt buatan sendiri) | salin (dari Bawaan)
    try {
      const j = JSON.parse(lemari.getItem(K_PILIH) || 'null');
      st.dipilih = Array.isArray(j) ? j.filter(x => typeof x === 'string') : [BAWAAN];
      st.terbuka = lemari.getItem(K_SELESAI) !== '1';
    } catch (e) { st.dipilih = [BAWAAN]; }
    const ubah = () => { if (opt.onUbah) opt.onUbah(); };

    async function panggil(path, body) {
      const o = {headers: {'Authorization': 'Bearer ' + opt.token()}};
      if (body !== undefined) { o.method = 'POST'; o.body = JSON.stringify(body); o.headers['Content-Type'] = 'application/json'; }
      const r = await fetch(path, o);
      const j = await r.json().catch(() => ({}));
      if (r.status === 401) throw new Error('Token salah.');
      if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
      return j;
    }
    function simpan() {
      try { lemari.setItem(K_PILIH, JSON.stringify(st.dipilih)); } catch (e) { /* abaikan */ }
    }
    function selesaiFlag(v) {
      try { if (v) lemari.setItem(K_SELESAI, '1'); else lemari.removeItem(K_SELESAI); } catch (e) { /* abaikan */ }
    }
    function terapkanDaftar(d) {
      st.daftar = d || [];
      const ada = new Set(st.daftar.map(p => p.id));
      st.dipilih = st.dipilih.filter(i => ada.has(i));       // prompt yang sudah dihapus dilepas dari pilihan
      st.dimuat = true; simpan();
    }
    async function muat() {
      if (st.memuat) return;
      st.memuat = true; st.galatMuat = '';
      try {
        const j = await panggil('/api/prompt');
        const adaTersimpan = lemari.getItem(K_PILIH) !== null;
        const dipilihAwal = st.dipilih.slice();
        terapkanDaftar(j.prompt); st.abaikan = j.abaikan || [];
        if (!adaTersimpan && !dipilihAwal.length) { st.dipilih = [BAWAAN]; simpan(); }   // pertama kali: bawaan dicentang
      } catch (e) { st.galatMuat = 'Gagal memuat daftar prompt: ' + e.message; }
      finally { st.memuat = false; gambar(); ubah(); }
    }

    /* ---------- tampilan ---------- */
    function totalKarakter() {
      return st.daftar.filter(p => st.dipilih.includes(p.id)).reduce((n, p) => n + (p.isi || '').length, 0);
    }
    function namaDipilih() { return st.daftar.filter(p => st.dipilih.includes(p.id)).map(p => p.nama); }
    function ringkasTeks() { const n = namaDipilih(); return n.length ? n.join(', ') : 'tanpa prompt (murni)'; }
    function gambar() {
      const tampilPanel = st.aktif && st.terbuka, tampilRingkas = st.aktif && !st.terbuka;
      $('promptBox').hidden = !tampilPanel;
      $('promptRingkas').hidden = !tampilRingkas;
      const lm = $('langkahModel'); if (lm) lm.hidden = tampilPanel;       // pilih model & Mulai menunggu "Selesai"
      if (tampilRingkas) $('promptRingkasTeks').textContent = 'Prompt: ' + ringkasTeks();
      if (!tampilPanel) return;
      const daftar = $('promptList'); daftar.textContent = '';
      for (const p of st.daftar) {
        const baris = el('div', 'promptBaris');
        const lab = el('label', 'nm'); const cek = el('input'); cek.type = 'checkbox';
        cek.checked = st.dipilih.includes(p.id); cek.setAttribute('aria-label', p.nama);
        cek.onchange = () => {
          st.dipilih = cek.checked ? st.dipilih.concat([p.id]) : st.dipilih.filter(i => i !== p.id);
          simpan(); gambarKet(); ubah();
        };
        const teksNama = el('span', '', p.nama + (p.bawaan ? ' · bawaan' : ''));
        if (p.catatan) teksNama.appendChild(el('small', 'cat', p.catatan));
        lab.append(cek, teksNama);
        lab.title = (p.catatan ? p.catatan + '\n\n' : '') + (p.isi || '').slice(0, 300);
        baris.appendChild(lab);
        const u = el('button', 'ubah', '(✎)'); u.type = 'button';
        u.setAttribute('aria-label', p.bawaan ? 'Salin prompt bawaan untuk diubah' : 'Ubah prompt ' + p.nama);
        u.title = p.bawaan ? 'Bawaan tidak bisa diubah; ini membuat salinan yang bisa diubah' : 'Ubah prompt';
        u.onclick = () => bukaForm(p.bawaan ? 'salin' : 'ubah', p);
        baris.appendChild(u);
        if (!p.bawaan) {
          const x = el('button', 'ekspor', '(⬇)'); x.type = 'button';
          x.setAttribute('aria-label', 'Unduh prompt ' + p.nama + ' untuk dibagikan'); x.title = 'Unduh sebagai berkas .json untuk dibagikan';
          x.onclick = () => ekspor(p);
          baris.appendChild(x);
          const h = el('button', 'hapus', '(−)'); h.type = 'button'; h.setAttribute('aria-label', 'Hapus prompt ' + p.nama);
          h.onclick = () => hapus(p);
          baris.appendChild(h);
        }
        daftar.appendChild(baris);
      }
      gambarKet();
    }
    function gambarKet() {
      const n = st.dipilih.length, k = totalKarakter();
      let t = st.galatMuat || (n
        ? 'Dipilih: ' + n + ' prompt · ±' + k + ' karakter' + (k > 3000 ? ' (panjang: memakan konteks model)' : '')
        : 'Tidak ada prompt dipilih: model berjalan tanpa prompt sistem (murni).');
      if (st.abaikan.length) t += ' · ' + st.abaikan.length + ' berkas di folder prompt dilewati (tidak valid: ' + st.abaikan.slice(0, 2).map(x => x.berkas).join(', ') + (st.abaikan.length > 2 ? ' ...' : '') + ')';
      $('promptKet').textContent = (st.info ? st.info + '\n' : '') + t;
    }

    /* ---------- aksi ---------- */
    async function hapus(p) {
      if (!window.confirm('Hapus prompt "' + p.nama + '"?')) return;
      try { const j = await panggil('/api/prompt/hapus', {id: p.id}); terapkanDaftar(j.prompt); }
      catch (e) { st.galatMuat = e.message; }
      gambar(); ubah();
    }
    async function ekspor(p) {            // unduh sebagai berkas .json (header Authorization tidak bisa lewat <a href>)
      try {
        const r = await fetch('/api/prompt/ekspor?id=' + encodeURIComponent(p.id), {headers: {'Authorization': 'Bearer ' + opt.token()}});
        if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || ('HTTP ' + r.status)); }
        const blob = await r.blob();
        const a = el('a'); a.href = URL.createObjectURL(blob); a.download = p.id + '.json';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        st.info = 'Diunduh: ' + p.id + '.json (kirim berkas ini ke siapa pun yang membutuhkan)';
      } catch (e) { st.info = 'Unduhan gagal: ' + e.message; }
      gambarKet();
    }
    async function impor(files) {
      let baru = 0; const lewat = []; let daftarAkhir = null, galat = '';
      for (const f of files) {
        try {
          const teks = await f.text();
          const j = await panggil('/api/prompt/impor', {teks});
          baru += (j.baru || []).length; daftarAkhir = j.prompt;
          for (const x of (j.dilewati || [])) lewat.push(x.nama + ': ' + x.alasan);
        } catch (e) { lewat.push(f.name + ': ' + e.message); }
      }
      if (daftarAkhir) terapkanDaftar(daftarAkhir);
      st.info = 'Impor: ' + baru + ' prompt ditambahkan' + (lewat.length ? ', ' + lewat.length + ' dilewati (' + lewat.slice(0, 3).join('; ') + (lewat.length > 3 ? ' ...' : '') + ')' : '');
      gambar(); ubah();
    }
    function bukaForm(jenis, p) {
      st.form = {jenis, id: jenis === 'ubah' ? p.id : null};
      $('promptFormJudul').textContent = jenis === 'ubah' ? 'Ubah prompt: ' + p.nama
        : jenis === 'salin' ? 'Salinan dari prompt bawaan (nama baru, isi boleh diubah)' : 'Prompt baru';
      $('promptNama').value = jenis === 'ubah' ? p.nama : jenis === 'salin' ? 'Salinan bawaan' : '';
      $('promptIsi').value = p ? (p.isi || '') : '';
      $('promptCatatan').value = jenis === 'ubah' ? (p.catatan || '') : '';
      $('promptGalat').textContent = ''; $('promptForm').hidden = false; $('promptNama').focus();
    }
    function tutupForm() {
      $('promptNama').value = ''; $('promptIsi').value = ''; $('promptCatatan').value = ''; $('promptGalat').textContent = '';
      $('promptForm').hidden = true; st.form = {jenis: 'baru', id: null};
    }
    async function simpanForm() {
      const nama = $('promptNama').value.trim(), isi = $('promptIsi').value.trim(), catatan = $('promptCatatan').value.trim(), galat = $('promptGalat');
      galat.textContent = '';
      if (!nama) { galat.textContent = 'Nama prompt wajib diisi.'; return; }
      if (!isi) { galat.textContent = 'Isi prompt wajib diisi.'; return; }
      $('btnPromptSimpan').disabled = true;
      try {
        const ubahAda = st.form.jenis === 'ubah';
        const j = await panggil(ubahAda ? '/api/prompt/ubah' : '/api/prompt', ubahAda ? {id: st.form.id, nama, isi, catatan} : {nama, isi, catatan});
        terapkanDaftar(j.prompt);
        if (!ubahAda && !st.dipilih.includes(j.baru.id)) st.dipilih = st.dipilih.concat([j.baru.id]);   // prompt baru langsung dicentang
        st.info = ''; simpan(); tutupForm(); gambar(); ubah();
      } catch (e) { galat.textContent = e.message; }
      finally { $('btnPromptSimpan').disabled = false; }
    }

    $('btnPromptBaru').onclick = () => {
      const f = $('promptForm');
      if (!f.hidden && st.form.jenis === 'baru') { tutupForm(); return; }            // ketuk lagi = tutup
      bukaForm('baru', null);
    };
    $('btnPromptSimpan').onclick = simpanForm;
    $('btnPromptImpor').onclick = () => $('promptBerkas').click();
    $('promptBerkas').onchange = () => { const f = Array.from($('promptBerkas').files || []); $('promptBerkas').value = ''; if (f.length) impor(f); };
    $('btnPromptBatal').onclick = tutupForm;
    $('btnPromptSelesai').onclick = () => { st.terbuka = false; selesaiFlag(true); tutupForm(); gambar(); ubah(); };
    $('btnPromptUbah').onclick = () => { st.terbuka = true; selesaiFlag(false); gambar(); ubah(); };

    return {
      /* panel berlaku bila skill Tanpa aktif; daftar dimuat dari server saat pertama kali dibutuhkan */
      atur(v) {
        const awal = st.aktif; st.aktif = !!v;
        if (st.aktif && !st.dimuat && !st.memuat) muat();
        if (awal !== st.aktif || st.dimuat) gambar();
      },
      ids: () => st.dipilih.slice(),
      nama: namaDipilih, ringkasTeks,
      terbuka: () => st.aktif && st.terbuka,
      aktif: () => st.aktif,
    };
  }
  window.PromptPilih = {pasang};
})();
