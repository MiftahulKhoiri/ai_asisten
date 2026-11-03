/* prompt_peran.js - tombol "+ prompt" di tiap peran Agent (Perencana, Pelaksana, Pemeriksa, Penjelas).
 *
 * Sama seperti prompt di Chat: daftar dengan kotak centang, "+ prompt" untuk menambah, (✎) mengubah,
 * (⬇) mengunduh .json untuk dibagikan, "⬆ Impor", dan (−) menghapus. Bedanya, tiap peran punya
 * daftarnya sendiri (server: prompt/agent/<peran>/) dan dua cara pakai:
 *   tambah  prompt bawaan peran tetap dipakai; yang dicentang ditambahkan di bawahnya
 *   ganti   yang dicentang menggantikan perilaku bawaan peran
 * Format keluaran yang dibaca program (JSON, blok === FILE ===) selalu ikut, apa pun pilihannya.
 * Tidak ada yang dicentang = prompt bawaan apa adanya.
 *
 *   const pp = PromptPeran.pasang({peran: 'perencana', label: 'Perencana', wadah: elemen, token: () => TOKEN,
 *                                  awal: {ids: [], mode: 'tambah'}, onUbah: ({ids, mode}) => ...});
 *   pp.muat()   ambil daftar dari server (dipanggil sekali token sudah ada)
 *   pp.ringkas()  teks ringkas pilihan sekarang
 */
(function () {
  'use strict';
  const BAWAAN = 'bawaan', MAKS_TEKS = 6000, PANJANG_PERINGATAN = 3000;
  function el(tag, cls, teks) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (teks !== undefined) e.textContent = teks;
    return e;
  }

  function pasang(opt) {
    const peran = opt.peran, label = opt.label || peran, wadah = opt.wadah;
    const awal = opt.awal || {};
    const st = {daftar: [], ids: Array.isArray(awal.ids) ? awal.ids.filter(x => typeof x === 'string') : [],
      mode: awal.mode === 'ganti' ? 'ganti' : 'tambah', terbuka: false, dimuat: false, memuat: false, galat: '', info: '',
      abaikan: [], form: {jenis: 'baru', id: null}, lihat: false};
    const URL_DASAR = '/api/agent/prompt';
    const kabarkan = () => { if (opt.onUbah) opt.onUbah({ids: st.ids.slice(), mode: st.mode}); };

    async function panggil(path, body) {
      const o = {headers: {'Authorization': 'Bearer ' + opt.token()}};
      if (body !== undefined) { o.method = 'POST'; o.body = JSON.stringify(body); o.headers['Content-Type'] = 'application/json'; }
      const r = await fetch(path, o);
      const j = await r.json().catch(() => ({}));
      if (r.status === 401) throw new Error('Token salah.');
      if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
      return j;
    }
    function terapkanDaftar(d) {
      st.daftar = d || [];
      const ada = new Set(st.daftar.filter(p => !p.bawaan).map(p => p.id));
      const sebelum = st.ids.length;
      st.ids = st.ids.filter(i => ada.has(i));          // prompt yang sudah dihapus dilepas dari pilihan
      st.dimuat = true;
      if (st.ids.length !== sebelum) kabarkan();
    }
    async function muat() {
      if (st.memuat) return;
      st.memuat = true; st.galat = '';
      try {
        const j = await panggil(URL_DASAR + '?peran=' + encodeURIComponent(peran));
        terapkanDaftar(j.prompt); st.abaikan = j.abaikan || [];
      } catch (e) { st.galat = 'Gagal memuat daftar prompt: ' + e.message; }
      finally { st.memuat = false; gambar(); }
    }

    /* ---------- data turunan ---------- */
    const dipakai = () => st.daftar.filter(p => !p.bawaan && st.ids.includes(p.id));
    const totalKarakter = () => dipakai().reduce((n, p) => n + (p.isi || '').length + 2, 0);
    function ringkas() {
      const n = dipakai().map(p => p.nama);
      if (!n.length) return st.dimuat || !st.ids.length ? 'bawaan' : st.ids.length + ' prompt';
      return (st.mode === 'ganti' ? 'ganti: ' : 'bawaan + ') + n.join(', ');
    }

    /* ---------- tampilan ---------- */
    const ringkasBaris = el('div', 'pp-ringkas');
    const ringkasTeks = el('span', 'pp-teks');
    const tombolBuka = el('button', 'btn abu kecil pp-buka', '+ prompt'); tombolBuka.type = 'button';
    tombolBuka.setAttribute('aria-expanded', 'false');
    ringkasBaris.append(ringkasTeks, tombolBuka);

    const panel = el('div', 'pp-panel'); panel.hidden = true;
    const modeBaris = el('div', 'pp-mode'); modeBaris.setAttribute('role', 'radiogroup'); modeBaris.setAttribute('aria-label', 'Cara memakai prompt ' + label);
    const tombolMode = {};
    for (const [m, nama] of [['tambah', 'Tambah ke bawaan'], ['ganti', 'Ganti bawaan']]) {
      const b = el('button', 'pp-modebtn', nama); b.type = 'button'; b.setAttribute('role', 'radio');
      b.onclick = () => { st.mode = m; kabarkan(); gambar(); };
      tombolMode[m] = b; modeBaris.appendChild(b);
    }
    const ketMode = el('p', 'redup kecil pp-ketmode');
    const kepala = el('div', 'pp-kepala');
    const tombolImpor = el('button', 'btn abu kecil', '⬆ Impor'); tombolImpor.type = 'button';
    tombolImpor.title = 'Impor prompt dari berkas .json (misalnya dari teman)';
    const tombolBaru = el('button', 'btn abu kecil', '+ prompt'); tombolBaru.type = 'button';
    const aksiKepala = el('span', 'pp-aksi'); aksiKepala.append(tombolImpor, tombolBaru);
    kepala.append(el('span', '', 'List prompt ' + label), aksiKepala);
    const berkas = el('input'); berkas.type = 'file'; berkas.accept = '.json,application/json'; berkas.multiple = true; berkas.hidden = true;

    const form = el('div', 'pp-form'); form.hidden = true;
    const formJudul = el('div', 'pp-formjudul', 'Prompt baru');
    const inNama = el('input'); inNama.type = 'text'; inNama.maxLength = 40; inNama.placeholder = 'Nama prompt'; inNama.setAttribute('aria-label', 'Nama prompt');
    const inIsi = el('textarea'); inIsi.rows = 6; inIsi.maxLength = 4000; inIsi.setAttribute('aria-label', 'Isi prompt');
    inIsi.placeholder = 'Isi prompt untuk ' + label + '. {waktu} akan diganti tanggal dan jam.';
    const inCatatan = el('input'); inCatatan.type = 'text'; inCatatan.maxLength = 200; inCatatan.placeholder = 'Catatan (opsional): cocok untuk apa / model apa'; inCatatan.setAttribute('aria-label', 'Catatan prompt');
    const galatForm = el('span', 'galat'); galatForm.setAttribute('role', 'alert');
    const tombolBatal = el('button', 'btn abu', 'Batal'); tombolBatal.type = 'button';
    const tombolSimpan = el('button', 'btn', 'Simpan'); tombolSimpan.type = 'button';
    const aksiForm = el('div', 'pp-aksiform'); aksiForm.append(galatForm, tombolBatal, tombolSimpan);
    form.append(formJudul, inNama, inIsi, inCatatan, aksiForm);

    const daftarEl = el('div', 'pp-daftar'); daftarEl.setAttribute('role', 'group'); daftarEl.setAttribute('aria-label', 'List prompt ' + label);
    const ket = el('p', 'redup kecil pp-ket');
    const tombolSelesai = el('button', 'btn pp-selesai', 'Selesai'); tombolSelesai.type = 'button';
    panel.append(modeBaris, ketMode, kepala, berkas, form, daftarEl, ket, tombolSelesai);
    wadah.append(ringkasBaris, panel);

    function gambarKet() {
      const n = dipakai().length, k = totalKarakter();
      let t = st.galat || (n
        ? 'Dipilih: ' + n + ' prompt · ±' + k + ' dari ' + MAKS_TEKS + ' karakter' + (k > MAKS_TEKS ? ' (terlalu panjang: kurangi yang dicentang)' : k > PANJANG_PERINGATAN ? ' (panjang: memakan konteks model)' : '')
        : 'Tidak ada yang dicentang: ' + label + ' memakai prompt bawaannya apa adanya.');
      if (st.abaikan.length) t += ' · ' + st.abaikan.length + ' berkas di folder peran ini dilewati (tidak valid: ' + st.abaikan.slice(0, 2).map(x => x.berkas).join(', ') + (st.abaikan.length > 2 ? ' ...' : '') + ')';
      ket.textContent = (st.info ? st.info + '\n' : '') + t;
    }
    function gambar() {
      ringkasTeks.textContent = 'Prompt: ' + ringkas();
      tombolBuka.textContent = st.terbuka ? 'Tutup' : '+ prompt';
      tombolBuka.setAttribute('aria-expanded', st.terbuka ? 'true' : 'false');
      panel.hidden = !st.terbuka;
      if (!st.terbuka) return;
      for (const m of ['tambah', 'ganti']) {
        tombolMode[m].classList.toggle('on', st.mode === m);
        tombolMode[m].setAttribute('aria-checked', st.mode === m ? 'true' : 'false');
      }
      ketMode.textContent = st.mode === 'ganti'
        ? 'Prompt yang kamu centang menggantikan perilaku bawaan ' + label + '. Format keluaran yang dibaca program tetap ditambahkan otomatis.'
        : 'Prompt bawaan ' + label + ' tetap dipakai; prompt yang kamu centang ditambahkan di bawahnya.';
      daftarEl.textContent = '';
      for (const p of st.daftar) {
        const baris = el('div', 'promptBaris pp-baris');
        const lab = el('label', 'nm');
        if (p.bawaan) {
          const nama = el('span', '', p.nama + ' · ' + (st.mode === 'tambah' || !dipakai().length ? 'aktif' : 'diganti'));
          if (p.catatan) nama.appendChild(el('small', 'cat', p.catatan));
          lab.appendChild(nama);
          lab.onclick = () => { st.lihat = !st.lihat; gambar(); };
          lab.title = 'Ketuk untuk melihat isi prompt bawaan';
        } else {
          const cek = el('input'); cek.type = 'checkbox'; cek.checked = st.ids.includes(p.id); cek.setAttribute('aria-label', p.nama);
          cek.onchange = () => {
            st.ids = cek.checked ? st.ids.concat([p.id]) : st.ids.filter(i => i !== p.id);
            kabarkan(); gambar();
          };
          const nama = el('span', '', p.nama);
          if (p.catatan) nama.appendChild(el('small', 'cat', p.catatan));
          lab.append(cek, nama);
          lab.title = (p.catatan ? p.catatan + '\n\n' : '') + (p.isi || '').slice(0, 300);
        }
        baris.appendChild(lab);
        const u = el('button', 'ubah', '(✎)'); u.type = 'button';
        u.setAttribute('aria-label', p.bawaan ? 'Salin prompt bawaan ' + label + ' untuk diubah' : 'Ubah prompt ' + p.nama);
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
        daftarEl.appendChild(baris);
        if (p.bawaan && st.lihat) daftarEl.appendChild(el('pre', 'pp-lihat', p.isi || ''));
      }
      gambarKet();
    }

    /* ---------- aksi ---------- */
    async function hapus(p) {
      if (!window.confirm('Hapus prompt "' + p.nama + '"?')) return;
      try { const j = await panggil(URL_DASAR + '/hapus', {peran, id: p.id}); terapkanDaftar(j.prompt); kabarkan(); }
      catch (e) { st.galat = e.message; }
      gambar();
    }
    async function ekspor(p) {            // header Authorization tidak bisa lewat <a href>, jadi diambil lalu diunduh
      try {
        const r = await fetch(URL_DASAR + '/ekspor?peran=' + encodeURIComponent(peran) + '&id=' + encodeURIComponent(p.id), {headers: {'Authorization': 'Bearer ' + opt.token()}});
        if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || ('HTTP ' + r.status)); }
        const blob = await r.blob();
        const a = el('a'); a.href = URL.createObjectURL(blob); a.download = peran + '-' + p.id + '.json';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        st.info = 'Diunduh: ' + peran + '-' + p.id + '.json (kirim berkas ini ke siapa pun yang membutuhkan)';
      } catch (e) { st.info = 'Unduhan gagal: ' + e.message; }
      gambarKet();
    }
    async function impor(files) {
      let baru = 0; const lewat = []; let daftarAkhir = null;
      for (const f of files) {
        try {
          const teks = await f.text();
          const j = await panggil(URL_DASAR + '/impor', {peran, teks});
          baru += (j.baru || []).length; daftarAkhir = j.prompt;
          for (const x of (j.dilewati || [])) lewat.push(x.nama + ': ' + x.alasan);
        } catch (e) { lewat.push(f.name + ': ' + e.message); }
      }
      if (daftarAkhir) terapkanDaftar(daftarAkhir);
      st.info = 'Impor: ' + baru + ' prompt ditambahkan' + (lewat.length ? ', ' + lewat.length + ' dilewati (' + lewat.slice(0, 3).join('; ') + (lewat.length > 3 ? ' ...' : '') + ')' : '');
      gambar();
    }
    function bukaForm(jenis, p) {
      st.form = {jenis, id: jenis === 'ubah' ? p.id : null};
      formJudul.textContent = jenis === 'ubah' ? 'Ubah prompt: ' + p.nama
        : jenis === 'salin' ? 'Salinan dari prompt bawaan (nama baru, isi boleh diubah)' : 'Prompt baru';
      inNama.value = jenis === 'ubah' ? p.nama : jenis === 'salin' ? 'Salinan bawaan ' + label : '';
      inIsi.value = p ? (p.isi || '') : '';
      inCatatan.value = jenis === 'ubah' ? (p.catatan || '') : '';
      galatForm.textContent = ''; form.hidden = false; inNama.focus();
    }
    function tutupForm() {
      inNama.value = ''; inIsi.value = ''; inCatatan.value = ''; galatForm.textContent = '';
      form.hidden = true; st.form = {jenis: 'baru', id: null};
    }
    async function simpanForm() {
      const nama = inNama.value.trim(), isi = inIsi.value.trim(), catatan = inCatatan.value.trim();
      galatForm.textContent = '';
      if (!nama) { galatForm.textContent = 'Nama prompt wajib diisi.'; return; }
      if (!isi) { galatForm.textContent = 'Isi prompt wajib diisi.'; return; }
      tombolSimpan.disabled = true;
      try {
        const ubahAda = st.form.jenis === 'ubah';
        const j = await panggil(ubahAda ? URL_DASAR + '/ubah' : URL_DASAR, ubahAda ? {peran, id: st.form.id, nama, isi, catatan} : {peran, nama, isi, catatan});
        terapkanDaftar(j.prompt);
        if (!ubahAda && !st.ids.includes(j.baru.id)) st.ids = st.ids.concat([j.baru.id]);   // prompt baru langsung dicentang
        st.info = ''; tutupForm(); kabarkan(); gambar();
      } catch (e) { galatForm.textContent = e.message; }
      finally { tombolSimpan.disabled = false; }
    }

    tombolBuka.onclick = () => {
      st.terbuka = !st.terbuka;
      if (st.terbuka && !st.dimuat && !st.memuat) muat();
      if (!st.terbuka) tutupForm();
      gambar();
    };
    tombolBaru.onclick = () => {
      if (!form.hidden && st.form.jenis === 'baru') { tutupForm(); return; }            // ketuk lagi = tutup
      bukaForm('baru', null);
    };
    tombolSimpan.onclick = simpanForm;
    tombolBatal.onclick = tutupForm;
    tombolImpor.onclick = () => berkas.click();
    berkas.onchange = () => { const f = Array.from(berkas.files || []); berkas.value = ''; if (f.length) impor(f); };
    tombolSelesai.onclick = () => { st.terbuka = false; tutupForm(); gambar(); };

    gambar();
    return {
      muat, ringkas, gambar,
      ids: () => st.ids.slice(), mode: () => st.mode, terbuka: () => st.terbuka,
      dimuat: () => st.dimuat, daftar: () => st.daftar.slice(),
    };
  }
  window.PromptPeran = {pasang, MAKS_TEKS};
})();
