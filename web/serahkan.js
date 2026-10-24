/* serahkan.js - serah terima chat -> Agent -> chat.
 *
 *   const s = Serahkan.pasang({token, chatId, wadah, sebelum, gulir, info, toast, sibuk, muatUlang, setelahSelesai});
 *
 * Tombol 🏭 menyusun brief dari diskusi (model chat), pengguna memeriksa/mengubah lalu menyetujuinya,
 * Agent mengerjakannya di server, dan hasilnya kembali ke obrolan sebagai kartu berisi berkas yang bisa
 * diunduh. Pengaturan model Agent dibaca dari penyimpanan yang sama dengan halaman Agent (ag_cfg).
 */
(function () {
  'use strict';
  const KUNCI_CFG = 'ag_cfg';
  const JALUR = [['otomatis', 'Otomatis'], ['buat', 'Buat'], ['perbaiki', 'Perbaiki'], ['cari_bug', 'Cari bug']];
  const IKON = {lolos: '✔', belum: '⚠', analisis: '🔎', batal: '⏹', error: '✖', butuh_info: '❓'};
  const LABEL = {lolos: 'dinyatakan jadi', belum: 'belum sempurna', analisis: 'analisis (tidak ada berkas diubah)',
    batal: 'dibatalkan', error: 'berhenti karena galat', butuh_info: 'butuh informasi darimu'};
  const NAMA_TAHAP = {diagnosa: 'Diagnosa', rencana: 'Perencana', tulis: 'Pelaksana', periksa: 'Pemeriksa', jelaskan: 'Penjelas'};

  function el(tag, cls, teks) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (teks !== undefined) e.textContent = teks;
    return e;
  }
  function ukuranTeks(n) { return n >= 10000 ? Math.round(n / 1000) + ' KB' : n >= 1000 ? (n / 1000).toFixed(1) + ' KB' : n + ' B'; }
  function tunggu(ms) { return new Promise(r => setTimeout(r, ms)); }

  /* pengaturan model Agent dari halaman Agent (null bila belum diatur) */
  function bacaCfg(lemari) {
    let c = {};
    try { c = JSON.parse((lemari || window.localStorage).getItem(KUNCI_CFG) || '{}'); } catch (e) { return null; }
    const mode = c.mode === 3 ? 3 : 2;
    if (!c.p || !c.e || (mode === 3 && !c.c)) return null;
    return {mode, model_p: c.p, model_e: c.e, model_c: mode === 3 ? c.c : c.p, maks: c.maks || 3,
      bongkar: c.bongkar !== false, uji: c.izinUji === true};
  }

  function pasang(opt) {
    const st = {kartu: null, ikuti: false, tombol: null};
    const wadah = opt.wadah;
    const gulir = opt.gulir || function () {};

    async function panggil(path, opsi) {
      opsi = Object.assign({}, opsi || {});
      opsi.headers = Object.assign({'Authorization': 'Bearer ' + opt.token()}, opsi.headers || {});
      return fetch(path, opsi);
    }
    async function json(path, body, metode) {
      const r = await panggil(path, body === undefined ? {} : {method: metode || 'POST', body: JSON.stringify(body),
        headers: {'Content-Type': 'application/json'}});
      const j = await r.json().catch(() => ({}));
      if (r.status === 401) throw new Error('Token salah.');
      if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
      return j;
    }
    function buangKartu() { if (st.kartu && st.kartu.parentNode) st.kartu.parentNode.removeChild(st.kartu); st.kartu = null; }
    function pasangKartu(k) { buangKartu(); st.kartu = k; wadah.appendChild(k); gulir(true); }

    /* ---------- tombol di header ---------- */
    const tombol = el('button', 'ikon', '🏭'); tombol.id = 'btnSerah'; tombol.type = 'button';
    tombol.title = 'Serahkan diskusi ini ke Agent'; tombol.setAttribute('aria-label', 'Serahkan ke Agent'); tombol.hidden = true;
    if (opt.sebelum && opt.sebelum.parentNode) opt.sebelum.parentNode.insertBefore(tombol, opt.sebelum);
    st.tombol = tombol;

    /* ---------- 1. brief untuk disetujui ---------- */
    async function mulai() {
      if (st.ikuti) { opt.toast && opt.toast('Agent masih bekerja.'); return; }
      if (opt.sibuk && opt.sibuk()) { opt.toast && opt.toast('Tunggu jawaban selesai dulu.'); return; }
      const cid = opt.chatId();
      if (!cid) return;
      const tunggu_ = el('div', 'serah'); tunggu_.append(el('div', 'jud', '🏭 Menyusun brief dari diskusi ...'),
        el('div', 'redup kecil', 'Model chat meringkas diskusi menjadi brief untuk Agent. Tunggu sebentar.'));
      tombol.disabled = true; pasangKartu(tunggu_);
      try {
        const d = await json('/api/handoff/ringkas', {id: cid});
        kartuBrief(d);
      } catch (e) {
        buangKartu(); opt.info && opt.info('⚠ ' + e.message, true);
      } finally { tombol.disabled = false; }
    }

    function kartuBrief(d) {
      const k = el('div', 'serah brief');
      k.appendChild(el('div', 'jud', '🏭 Serahkan ke Agent'));
      k.appendChild(el('div', 'redup kecil', 'Periksa dan ubah brief ini. Agent hanya membaca brief ini (dan berkas lampiran), bukan seluruh diskusi.'));
      if (d.otomatis === false) k.appendChild(el('div', 'redup kecil', '⚠ Model tidak berhasil meringkas; brief disusun dari pesanmu. Rapikan dulu bila perlu.'));
      const isi = el('textarea'); isi.value = d.ringkasan || ''; isi.setAttribute('aria-label', 'Brief untuk Agent');
      k.appendChild(isi);
      // jalur kerja
      let jalur = 'otomatis';
      const bar = el('div', 'jalur'); bar.setAttribute('role', 'radiogroup');
      const tombolJalur = {};
      function gambarJalur() { JALUR.forEach(([id]) => tombolJalur[id].setAttribute('aria-checked', id === jalur ? 'true' : 'false')); }
      JALUR.forEach(([id, nama]) => {
        const b = el('button', '', nama); b.type = 'button'; b.setAttribute('role', 'radio'); tombolJalur[id] = b;
        b.onclick = () => { jalur = id; gambarJalur(); }; bar.appendChild(b);
      });
      gambarJalur(); k.appendChild(bar);
      if (d.jalur_label) k.appendChild(el('div', 'redup kecil', 'Otomatis akan memilih: ' + d.jalur_label + (d.alasan ? ' (' + d.alasan + ')' : '')));
      if ((d.lampiran || []).length) {
        k.appendChild(el('div', 'redup kecil', '📎 Bahan kerja dari lampiran obrolan: ' + d.lampiran.map(x => x.nama).slice(0, 8).join(', ')
          + (d.lampiran.length > 8 ? ' ... (' + d.lampiran.length + ' berkas)' : '')));
      }
      // lanjutkan hasil Agent sebelumnya
      let cekLanjut = null;
      if (d.lanjut) {
        const l = el('label', 'cek'); cekLanjut = el('input'); cekLanjut.type = 'checkbox'; cekLanjut.checked = true;
        l.append(cekLanjut, el('span', '', 'Lanjutkan dari hasil Agent sebelumnya (' + (d.lanjut.judul || d.lanjut.run) + ')'));
        k.appendChild(l);
      }
      const cfg = bacaCfg();
      k.appendChild(el('div', 'redup kecil', cfg
        ? 'Model Agent: ' + cfg.model_p + ' / ' + cfg.model_e + (cfg.mode === 3 ? ' / ' + cfg.model_c : '') + ' · maks ' + cfg.maks
          + ' putaran · uji jalan: ' + (cfg.uji ? 'diizinkan' : 'mati') + '. Ubah di halaman Agent.'
        : '⚠ Model Agent belum diatur. Buka halaman Agent, pilih model, lalu kembali ke sini.'));
      const lm = el('label', 'cek'); const cekMuat = el('input'); cekMuat.type = 'checkbox'; cekMuat.checked = true;
      lm.append(cekMuat, el('span', '', 'Muat ulang model chat setelah Agent selesai (agar diskusi bisa dilanjutkan)'));
      k.appendChild(lm);
      k.appendChild(el('div', 'redup kecil', 'Model chat dilepas dari memori selama Agent bekerja; Agent berjalan di server dan tetap lanjut walau halaman ditutup.'));
      const galat = el('div', 'galat'); galat.hidden = true; k.appendChild(galat);
      const aksi = el('div', 'aksi');
      const kirim = el('button', 'btn', 'Setujui & kirim ke Agent'); kirim.type = 'button'; kirim.disabled = !cfg;
      const batal = el('button', 'btn abu', 'Batal'); batal.type = 'button';
      batal.onclick = () => buangKartu();
      kirim.onclick = async () => {
        const tugas = isi.value.trim();
        if (!tugas) { galat.textContent = 'Brief tidak boleh kosong.'; galat.hidden = false; return; }
        kirim.disabled = true; galat.hidden = true;
        const body = Object.assign({id: opt.chatId(), tugas, jalur, muat_ulang: cekMuat.checked}, cfg);
        if (cekLanjut && cekLanjut.checked) body.lanjut = d.lanjut.run;
        try {
          const j = await json('/api/handoff/kirim', body);
          buangKartu();
          if (opt.muatUlang) await opt.muatUlang();        // tampilkan pesan "Diserahkan ke Agent" dari server
          ikuti(j.sesi);
        } catch (e) { galat.textContent = e.message; galat.hidden = false; kirim.disabled = false; }
      };
      aksi.append(kirim, batal); k.appendChild(aksi);
      pasangKartu(k);
    }

    /* ---------- 2. memantau Agent bekerja ---------- */
    function kartuProgres() {
      const k = el('div', 'serah progres');
      k.appendChild(el('div', 'jud', '🏭 Agent bekerja ...'));
      const baris = el('div', 'redup kecil', 'Menghubungi Agent ...');
      const tahap = el('div', 'tahap');
      const aksi = el('div', 'aksi');
      const lihat = el('a', 'btn abu', 'Lihat detail di Agent'); lihat.href = 'agent.html';
      const stop = el('button', 'btn abu', 'Stop'); stop.type = 'button';
      stop.onclick = async () => { try { await json('/api/stop', {}); } catch (e) { opt.toast && opt.toast(e.message); } };
      aksi.append(lihat, stop);
      k.append(k.firstChild, baris, tahap, aksi);
      k.baris = baris; k.tahap = tahap;
      return k;
    }
    function gambarTahap(k, urut, selesai, aktif) {
      k.tahap.textContent = '';
      urut.forEach(t => {
        const kelas = t === aktif ? 'akt' : selesai.has(t) ? 'sel' : '';
        k.tahap.appendChild(el('span', kelas, (selesai.has(t) && t !== aktif ? '✓ ' : '') + (NAMA_TAHAP[t] || t)));
      });
    }
    async function ikuti(sesi) {
      if (st.ikuti) return;
      st.ikuti = true;
      const k = kartuProgres(); pasangKartu(k);
      let urut = [], selesai = new Set(), aktif = null, next = 0, putus = false, putaran = '';
      try {
        while (true) {
          let j = null;
          try {
            const r = await panggil('/api/agent/event?sesi=' + encodeURIComponent(sesi) + '&dari=' + next + '&tunggu=20');
            if (r.status === 410 || r.status === 404) break;                    // proses sudah tidak ada: lihat hasil di obrolan
            if (r.status === 401) throw new Error('Token salah.');
            if (r.ok) j = await r.json().catch(() => null);
          } catch (e) { if (e.message === 'Token salah.') throw e; }
          if (!j) {
            if (!putus) { putus = true; k.baris.textContent = 'Terputus, mencoba menyambung lagi ... (Agent tetap bekerja di server)'; }
            await tunggu((window.SERAHKAN_JEDA_ULANG !== undefined) ? window.SERAHKAN_JEDA_ULANG : 3000);
            continue;
          }
          putus = false;
          for (const ev of (j.events || [])) {
            if (ev.t === 'jalur') { urut = (ev.urut || []).map(x => x.kunci); k.baris.textContent = 'Jalur: ' + ev.label; }
            else if (ev.t === 'tahap') {
              if (aktif) selesai.add(aktif);
              aktif = ev.tahap; k.baris.textContent = (ev.peran || NAMA_TAHAP[ev.tahap] || ev.tahap) + ' bekerja' + (putaran ? ' · ' + putaran : '') + ' ...';
            } else if (ev.t === 'putaran') { putaran = 'putaran ' + ev.n + '/' + ev.maks; }
            else if (ev.t === 'diagnosa') { selesai.add('diagnosa'); k.baris.textContent = ev.ok ? 'Diagnosa: tidak ada bug nyata' : 'Diagnosa: ' + (ev.masalah || []).length + ' temuan'; }
            else if (ev.t === 'tanya') { k.baris.textContent = 'Agent butuh informasi.'; }
            gambarTahap(k, urut, selesai, aktif);
          }
          next = j.next;
          if (j.habis) break;
        }
      } catch (e) {
        opt.info && opt.info('⚠ ' + e.message, true);
      } finally {
        st.ikuti = false; buangKartu();
        if (opt.muatUlang) await opt.muatUlang();       // hasil sudah ditulis server ke obrolan
        if (opt.setelahSelesai) opt.setelahSelesai();
      }
    }

    /* halaman dibuka lagi saat Agent masih bekerja untuk obrolan ini */
    function pulihkan(agent) {
      if (!agent || !agent.aktif || st.ikuti) return;
      if (agent.chat_id && agent.chat_id === opt.chatId()) ikuti(agent.sesi);
    }

    /* ---------- 3. hasil di obrolan ---------- */
    async function unduh(url, nama) {
      try {
        const r = await panggil(url);
        if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || ('HTTP ' + r.status)); }
        const blob = await r.blob();
        const a = el('a'); a.href = URL.createObjectURL(blob); a.download = nama;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      } catch (e) { opt.toast && opt.toast('Unduhan gagal: ' + e.message); }
    }
    function kartuHasil(h) {
      const k = el('div', 'serah hasil');
      k.appendChild(el('div', 'jud', (IKON[h.status] || '•') + ' Hasil Agent' + (h.judul ? ' · ' + h.judul : '')));
      k.appendChild(el('div', 'redup kecil', (LABEL[h.status] || h.status) + (h.putaran ? ' · ' + h.putaran + ' putaran' : '')));
      const berkas = h.berkas || [];
      berkas.slice(0, 20).forEach(b => {
        const r = el('div', 'berkas'); r.append(el('span', 'nm', b.nama), el('small', '', ukuranTeks(b.ukuran || 0)));
        const u = el('button', 'btn abu', '⬇'); u.type = 'button'; u.setAttribute('aria-label', 'Unduh ' + b.nama);
        u.onclick = () => unduh('/api/agent/run/' + h.run + '/unduh?berkas=' + encodeURIComponent(b.nama), b.nama.replace(/\//g, '_'));
        r.appendChild(u); k.appendChild(r);
      });
      if (berkas.length > 20) k.appendChild(el('div', 'redup kecil', '... dan ' + (berkas.length - 20) + ' berkas lain (ada di zip)'));
      if (h.status === 'butuh_info') k.appendChild(el('div', 'redup kecil', 'Jawab pertanyaannya di chat, lalu serahkan lagi ke Agent dengan tombol 🏭.'));
      const aksi = el('div', 'aksi');
      if (berkas.length) {
        const z = el('button', 'btn', '⬇ Unduh semua (.zip)'); z.type = 'button';
        z.onclick = () => unduh('/api/agent/run/' + h.run + '/unduh', (h.judul || h.run).replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 40) + '.zip');
        aksi.appendChild(z);
      }
      if (h.run) { const a = el('a', 'btn abu', 'Lihat proses'); a.href = 'agent.html?run=' + encodeURIComponent(h.run); aksi.appendChild(a); }
      k.appendChild(aksi);
      return k;
    }

    tombol.onclick = mulai;
    return {
      mulai, pulihkan, kartuHasil, unduh,
      tampilkan: v => { tombol.hidden = !v; },
      aktif: () => st.ikuti,
    };
  }
  window.Serahkan = {pasang, bacaCfg};
})();
