/* koneksi.js - pengaturan koneksi ke llama-server atau penyedia model online (alamat + API key).
 *
 *   const k = Koneksi.pasang({token, wadah, toast, setelahUbah});
 *   k.perbarui(status.koneksi);   // dari /api/status atau /api/agent/status
 *   k.buka();                     // membuka dialog
 *
 * `wadah` diisi satu baris ringkas ("Server model: ... [Atur koneksi]"). Kunci API hanya dikirim ke
 * server saat disimpan atau diuji; server tidak pernah mengirimnya kembali (hanya tahu ada/tidaknya).
 */
(function () {
  'use strict';
  const JENIS = {llama: 'llama-server', online: 'penyedia online'};

  function el(tag, cls, teks) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (teks !== undefined) e.textContent = teks;
    return e;
  }

  function pasang(opt) {
    const st = {k: null, dlg: null, hapusKey: false, sibuk: false};
    const toast = opt.toast || function () {};

    async function json(path, body) {
      const r = await fetch(path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: Object.assign({'Authorization': 'Bearer ' + opt.token()},
          body === undefined ? {} : {'Content-Type': 'application/json'}),
        body: body === undefined ? undefined : JSON.stringify(body)});
      const j = await r.json().catch(() => ({}));
      if (r.status === 401) throw new Error('Token salah.');
      if (!r.ok && !j.error) throw new Error('HTTP ' + r.status);
      return j;
    }

    /* ---------- baris ringkas ---------- */
    let teks = null;
    if (opt.wadah) {
      opt.wadah.classList.add('kon-baris');
      teks = el('span', 'kon-teks');
      const b = el('button', 'tautan kon-atur', 'Atur koneksi');
      b.type = 'button';
      b.onclick = () => buka();
      opt.wadah.append(teks, ' ', b);
    }
    function ringkas(k) {
      if (!k) return '';
      return 'Server model: ' + k.alamat + ' · ' + (JENIS[k.jenis] || k.jenis) + (k.key_ada ? ' · API key ✔' : '');
    }
    function perbarui(k) {
      if (k) st.k = k;
      if (teks) teks.textContent = ringkas(st.k);
    }

    /* ---------- dialog ---------- */
    function bangun() {
      const tirai = el('div', 'kon-tirai');
      tirai.hidden = true;
      const dlg = el('div', 'kon-dlg');
      dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true'); dlg.setAttribute('aria-labelledby', 'konJudul');
      const judul = el('h3', '', 'Koneksi model'); judul.id = 'konJudul';
      const ket = el('p', 'redup kecil', 'Isi alamat llama-server (yang dinyalakan ./llama_server.sh) atau penyedia online yang kompatibel OpenAI. ' +
        'Semua model yang dilaporkan server akan tampil di daftar model.');

      const lAlamat = el('label', 'kon-label', 'Alamat server'); lAlamat.htmlFor = 'konAlamat';
      const inAlamat = el('input'); inAlamat.id = 'konAlamat'; inAlamat.type = 'text'; inAlamat.inputMode = 'url';
      inAlamat.autocomplete = 'off'; inAlamat.autocapitalize = 'none'; inAlamat.spellcheck = false; inAlamat.maxLength = 300;
      inAlamat.placeholder = 'http://127.0.0.1:8080  atau  https://api.openai.com/v1';

      const lJenis = el('div', 'kon-label', 'Jenis server');
      const seg = el('div', 'seg kon-seg'); seg.setAttribute('role', 'radiogroup');
      const bJenis = {};
      for (const [id, nama, kecil] of [['llama', 'llama-server', 'Lokal / jaringan sendiri'], ['online', 'Penyedia online', 'OpenAI, OpenRouter, dll']]) {
        const b = el('button'); b.type = 'button'; b.dataset.jenis = id; b.setAttribute('role', 'radio');
        b.append(el('b', '', nama), el('small', '', kecil));
        b.onclick = () => aturJenis(id);
        bJenis[id] = b; seg.appendChild(b);
      }

      const lKunci = el('label', 'kon-label', 'API key'); lKunci.htmlFor = 'konKunci';
      const inKunci = el('input'); inKunci.id = 'konKunci'; inKunci.type = 'password'; inKunci.autocomplete = 'off';
      inKunci.autocapitalize = 'none'; inKunci.spellcheck = false; inKunci.maxLength = 500;
      const kunciKet = el('p', 'redup kecil kon-kunci-ket');
      const bHapusKey = el('button', 'tautan', 'Hapus API key tersimpan'); bHapusKey.type = 'button';
      bHapusKey.onclick = () => { st.hapusKey = true; inKunci.value = ''; gambarKunci(); };

      const hasil = el('div', 'kon-hasil'); hasil.setAttribute('role', 'status'); hasil.setAttribute('aria-live', 'polite');
      const aksi = el('div', 'kon-aksi');
      const bUji = el('button', 'btn abu', 'Uji koneksi'); bUji.type = 'button';
      const bSimpan = el('button', 'btn', 'Simpan'); bSimpan.type = 'button';
      const bReset = el('button', 'btn abu', 'Pakai bawaan'); bReset.type = 'button';
      bReset.title = 'Hapus pengaturan dari web dan kembali ke nilai awal (LLAMA_BASE_URL)';
      const bTutup = el('button', 'btn abu', 'Tutup'); bTutup.type = 'button';
      aksi.append(bUji, bSimpan, bReset, bTutup);

      dlg.append(judul, ket, lAlamat, inAlamat, lJenis, seg, lKunci, inKunci, kunciKet, bHapusKey, hasil, aksi);
      tirai.appendChild(dlg);
      document.body.appendChild(tirai);
      const d = {tirai, dlg, inAlamat, inKunci, kunciKet, bHapusKey, hasil, bUji, bSimpan, bReset, bTutup, bJenis, jenis: 'llama'};

      tirai.addEventListener('mousedown', e => { if (e.target === tirai) tutup(); });
      tirai.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); tutup(); } });
      bTutup.onclick = tutup;
      bUji.onclick = uji;
      bSimpan.onclick = simpan;
      bReset.onclick = reset;
      inKunci.addEventListener('input', () => { if (inKunci.value) st.hapusKey = false; gambarKunci(); });
      return d;
    }

    function aturJenis(id) {
      const d = st.dlg;
      d.jenis = id;
      for (const [k, b] of Object.entries(d.bJenis)) { b.classList.toggle('on', k === id); b.setAttribute('aria-checked', k === id ? 'true' : 'false'); }
    }
    function gambarKunci() {
      const d = st.dlg, ada = !!(st.k && st.k.key_ada);
      d.inKunci.placeholder = ada && !st.hapusKey ? '•••••••• (tersimpan)' : 'Tempel API key (boleh kosong untuk llama-server lokal)';
      d.kunciKet.textContent = st.hapusKey ? 'API key tersimpan akan dihapus saat Simpan.'
        : ada ? 'Kosongkan kolom ini bila tidak ingin mengubah key yang tersimpan.'
          : 'Key disimpan di server (pengaturan.json), tidak ditampilkan lagi, dan hanya dikirim ke alamat di atas.';
      d.bHapusKey.hidden = !ada || st.hapusKey;
    }
    function tulis(kelas, teksPesan, tambahan) {
      const h = st.dlg.hasil;
      h.className = 'kon-hasil ' + kelas;
      h.textContent = teksPesan;
      for (const t of tambahan || []) h.appendChild(el('div', 'redup kecil', t));
    }
    function badan() {
      const d = st.dlg, b = {alamat: d.inAlamat.value.trim(), jenis: d.jenis};
      if (d.inKunci.value) b.key = d.inKunci.value.trim();
      else if (st.hapusKey) b.key = '';
      return b;
    }
    function kunci(sibuk) {
      st.sibuk = sibuk;
      const d = st.dlg;
      d.bUji.disabled = d.bSimpan.disabled = d.bReset.disabled = sibuk;
    }

    async function uji() {
      if (st.sibuk) return;
      kunci(true); tulis('', 'Menghubungi server ...');
      try {
        const j = await json('/api/koneksi/uji', badan());
        if (!j.ok) { tulis('gagal', '✖ ' + (j.error || 'Gagal terhubung')); return; }
        const sub = [];
        sub.push(j.router ? 'Mode router: model dimuat dan dibongkar otomatis saat dipakai.'
          : 'Tanpa mode router: model dipakai langsung (tidak ada muat/bongkar).');
        if (j.contoh && j.contoh.length) sub.push('Contoh: ' + j.contoh.join(', ') + (j.jumlah > j.contoh.length ? ' ...' : ''));
        if (!j.router && st.dlg.jenis === 'llama') sub.push('Bila ini penyedia online (OpenAI, OpenRouter, dll), pilih jenis "Penyedia online".');
        if (j.peringatan) sub.push('⚠ ' + j.peringatan);
        tulis('ok', '✔ Terhubung · ' + j.jumlah + ' model', sub);
      } catch (e) { tulis('gagal', '✖ ' + e.message); }
      finally { kunci(false); }
    }
    async function simpan() {
      if (st.sibuk) return;
      kunci(true); tulis('', 'Menyimpan ...');
      try {
        const j = await json('/api/koneksi', badan());
        if (!j.ok) { tulis('gagal', '✖ ' + (j.error || 'Gagal menyimpan')); return; }
        st.hapusKey = false; st.dlg.inKunci.value = '';
        perbarui(j.koneksi);
        toast(j.tersimpan === false ? (j.peringatan || 'Berlaku, tapi tidak tersimpan') : 'Koneksi disimpan');
        tutup();
        if (opt.setelahUbah) opt.setelahUbah(j.koneksi);
      } catch (e) { tulis('gagal', '✖ ' + e.message); }
      finally { kunci(false); }
    }
    async function reset() {
      if (st.sibuk) return;
      if (!confirm('Hapus pengaturan koneksi dari web dan kembali ke nilai awal?')) return;
      kunci(true);
      try {
        const j = await json('/api/koneksi/reset', {});
        if (!j.ok) { tulis('gagal', '✖ ' + (j.error || 'Gagal')); return; }
        st.hapusKey = false; st.dlg.inKunci.value = '';
        perbarui(j.koneksi);
        toast('Kembali ke koneksi bawaan');
        tutup();
        if (opt.setelahUbah) opt.setelahUbah(j.koneksi);
      } catch (e) { tulis('gagal', '✖ ' + e.message); }
      finally { kunci(false); }
    }

    function isi() {
      const d = st.dlg, k = st.k || {alamat: '', jenis: 'llama', key_ada: false, sumber: 'bawaan'};
      d.inAlamat.value = k.alamat || '';
      d.inKunci.value = '';
      st.hapusKey = false;
      aturJenis(k.jenis === 'online' ? 'online' : 'llama');
      gambarKunci();
      d.bReset.hidden = k.sumber !== 'web';
      d.hasil.className = 'kon-hasil';
      d.hasil.textContent = k.peringatan ? '⚠ ' + k.peringatan : '';
    }
    async function buka() {
      if (!st.dlg) st.dlg = bangun();
      try { perbarui(await json('/api/koneksi')); } catch (e) { toast(e.message); }
      isi();
      st.dlg.tirai.hidden = false;
      st.dlg.inAlamat.focus();
    }
    function tutup() {
      if (st.dlg) st.dlg.tirai.hidden = true;
    }

    return {perbarui, buka, tutup, ringkas};
  }

  window.Koneksi = {pasang: pasang};
})();
