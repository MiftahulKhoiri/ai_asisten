/* prompt.js - pilihan prompt untuk skill Tanpa (layar "Mulai sesi" di halaman chat).
 *
 * Daftar prompt disimpan di server (prompt.json), jadi sama di semua perangkat. Setiap prompt punya
 * kotak centang: boleh memilih beberapa (digabung berurutan), tidak memilih satu pun = model berjalan
 * tanpa prompt sistem (murni). Tombol "+ prompt" membuka kolom nama dan isi; "(−)" menghapus;
 * "Selesai" menutup panel dan melanjutkan ke pilih model.
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
    const st = {aktif: false, daftar: [], dipilih: [], terbuka: true, dimuat: false, memuat: false, galatMuat: ''};
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
        terapkanDaftar(j.prompt);
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
        lab.append(cek, el('span', '', p.nama + (p.bawaan ? ' · bawaan' : '')));
        lab.title = (p.isi || '').slice(0, 300);
        baris.appendChild(lab);
        if (!p.bawaan) {
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
      $('promptKet').textContent = t;
    }

    /* ---------- aksi ---------- */
    async function hapus(p) {
      if (!window.confirm('Hapus prompt "' + p.nama + '"?')) return;
      try { const j = await panggil('/api/prompt/hapus', {id: p.id}); terapkanDaftar(j.prompt); }
      catch (e) { st.galatMuat = e.message; }
      gambar(); ubah();
    }
    async function simpanBaru() {
      const nama = $('promptNama').value.trim(), isi = $('promptIsi').value.trim(), galat = $('promptGalat');
      galat.textContent = '';
      if (!nama) { galat.textContent = 'Nama prompt wajib diisi.'; return; }
      if (!isi) { galat.textContent = 'Isi prompt wajib diisi.'; return; }
      $('btnPromptSimpan').disabled = true;
      try {
        const j = await panggil('/api/prompt', {nama, isi});
        terapkanDaftar(j.prompt);
        if (!st.dipilih.includes(j.baru.id)) st.dipilih = st.dipilih.concat([j.baru.id]);   // langsung dicentang
        simpan();
        $('promptNama').value = ''; $('promptIsi').value = ''; $('promptForm').hidden = true;
        gambar(); ubah();
      } catch (e) { galat.textContent = e.message; }
      finally { $('btnPromptSimpan').disabled = false; }
    }

    $('btnPromptBaru').onclick = () => {
      const f = $('promptForm'); f.hidden = !f.hidden;
      if (!f.hidden) { $('promptGalat').textContent = ''; $('promptNama').focus(); }
    };
    $('btnPromptSimpan').onclick = simpanBaru;
    $('btnPromptSelesai').onclick = () => { st.terbuka = false; selesaiFlag(true); $('promptForm').hidden = true; gambar(); ubah(); };
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
