(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  let TOKEN = localStorage.getItem('aa_token') || '';
  let layar = '', sibuk = false, models = [], statusSrv = null, daftarSig = '';
  let lanjutId = null, lanjutJudul = '', awalTanya = null;
  const cfg = {mode: 2, p: '', e: '', c: '', maks: 3, bongkar: true, uji: true};

  /* ---------- util ---------- */
  function el(tag, kelas, teks) {
    const e = document.createElement(tag);
    if (kelas) e.className = kelas;
    if (teks !== undefined) e.textContent = teks;
    return e;
  }
  function esc(s) {
    return s.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  }
  function md(s) {
    return s.split('```').map((p, i) => {
      if (i % 2 === 1) {
        const nl = p.indexOf('\n');
        const kode = (nl >= 0 && /^[\w+-]*$/.test(p.slice(0, nl).trim())) ? p.slice(nl + 1) : p;
        return '<div class="kode"><button type="button" class="salin">Salin</button><pre><code>' +
          esc(kode.replace(/\n$/, '')) + '</code></pre></div>';
      }
      return esc(p)
        .replace(/`([^`\n]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    }).join('');
  }
  async function salinTeks(teks) {
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(teks); return true; }
    } catch (e) { /* lanjut ke cara cadangan */ }
    try {   // http biasa (alamat IP lokal) tidak punya clipboard API
      const t = document.createElement('textarea');
      t.value = teks; t.setAttribute('readonly', '');
      t.style.cssText = 'position:fixed;top:0;left:0;opacity:0;font-size:16px';
      document.body.appendChild(t); t.select(); t.setSelectionRange(0, teks.length);
      const ok = document.execCommand('copy'); t.remove(); return ok;
    } catch (e) { return false; }
  }
  let toastT = null;
  function toast(m) {
    const t = $('toast'); t.textContent = m; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 3500);
  }
  function gulir(paksa) {
    const b = $('pesan');
    if (paksa || b.scrollHeight - b.scrollTop - b.clientHeight < 140) b.scrollTop = b.scrollHeight;
  }
  function ribu(n) { return n >= 1000 ? (n / 1000).toFixed(1).replace('.0', '') + 'k' : String(n); }
  function gb(mb) { return mb ? (mb / 1024).toFixed(1) + ' GB' : '?'; }

  /* ---------- log langsung: lencana di pojok atas + panel rincian ---------- */
  const LOG_MAKS = 600;
  const NAMA_STATE = {belum: 'belum dimuat', memuat: 'sedang dimuat', termuat: 'termuat di memori',
    membongkar: 'sedang dibongkar', dibongkar: 'sudah dibongkar'};
  const aktv = {label: '', model: '', mulai: 0, selesai: false, gagal: false, izin: false};
  let logList = [], logMulai = 0, logAkhir = 0, modelState = {}, peranModel = {};
  let keluaran = '', keluaranJudul = '', panelBuka = false;

  function mmss(ms) {
    const d = Math.max(0, Math.floor(ms / 1000));
    return Math.floor(d / 60) + ':' + String(d % 60).padStart(2, '0');
  }
  function gambarBarisLog(e) {
    const d = el('div', 'lg ' + e.kelas);
    d.append(el('span', 'lw', mmss(e.t)), el('span', 'li', e.ikon), el('span', 'lt', e.teks));
    e.el = d;
    const sc = $('logIsi'), dekat = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 80;
    $('logDaftar').appendChild(d);
    if (dekat) sc.scrollTop = sc.scrollHeight;
  }
  function catatLog(ikon, teks, kelas) {
    const e = {t: Date.now() - logMulai, ikon, teks, kelas: kelas || '', el: null};
    logList.push(e);
    if (logList.length > LOG_MAKS) { const buang = logList.shift(); if (buang.el) buang.el.remove(); }
    if (panelBuka) { gambarBarisLog(e); gambarRingkas(); }
    return e;
  }
  function ubahLog(e, teks) {
    e.teks = teks;
    if (e.el) e.el.querySelector('.lt').textContent = teks;
  }
  function setModel(nama, state) {
    if (!nama) return;
    modelState[nama] = state;
    if (panelBuka) gambarModel();
  }
  function setAktif(label, model, izin) {
    aktv.label = label; aktv.model = model || ''; aktv.mulai = Date.now(); aktv.izin = !!izin;
    renderLencana();
  }
  function akhiriLog(label, gagal) {
    aktv.selesai = true; aktv.gagal = !!gagal; aktv.label = label; aktv.model = ''; aktv.izin = false;
    logAkhir = Date.now();
    renderLencana();
  }
  function resetLog() {
    logList = []; logMulai = 0; logAkhir = 0; keluaran = ''; keluaranJudul = '';
    $('logDaftar').innerHTML = '';
    tutupPanel(); renderLencana();
  }
  function mulaiLog(teks) {
    logList = []; $('logDaftar').innerHTML = ''; logMulai = Date.now(); logAkhir = 0;
    keluaran = ''; keluaranJudul = ''; aktv.selesai = false; aktv.gagal = false;
    modelState = {}; peranModel = {};
    const pm = cfg.mode === 3
      ? [[cfg.p, 'Perencana · Penjelas'], [cfg.e, 'Pelaksana'], [cfg.c, 'Pemeriksa']]
      : [[cfg.p, 'Perencana · Pemeriksa · Penjelas'], [cfg.e, 'Pelaksana']];
    for (const [n, peran] of pm) {
      peranModel[n] = peranModel[n] ? peranModel[n] + ' · ' + peran : peran;
      modelState[n] = 'belum';
    }
    setAktif('Menghubungi server', '');
    catatLog('▶', 'Perintah dikirim: ' + teks.replace(/\s+/g, ' ').slice(0, 80));
    if (panelBuka) bukaPanel();
  }
  function renderLencana() {
    const b = $('lencanaLog');
    b.hidden = !logMulai; $('isiPesan').classList.toggle('ada-pil', !!logMulai);
    b.classList.toggle('selesai', aktv.selesai && !aktv.gagal);
    b.classList.toggle('gagal', aktv.selesai && aktv.gagal);
    b.classList.toggle('izin', !aktv.selesai && aktv.izin);
    if (!logMulai) return;
    const k = $('lencanaKata');
    if (k.textContent !== aktv.label) k.textContent = aktv.label;   // jangan ganti node tiap detik (pembaca layar)
    const d = Math.floor((Date.now() - aktv.mulai) / 1000);
    $('lencanaSub').textContent = aktv.selesai ? 'ketuk untuk lihat log'
      : (aktv.model ? aktv.model + ' · ' : '') + d + ' dtk';
    if (panelBuka) gambarSekarang();
  }
  function gambarRingkas() {
    $('logRingkas').textContent = 'Total ' + mmss((logAkhir || Date.now()) - logMulai) + ' · ' + logList.length + ' baris';
  }
  function gambarSekarang() {
    const d = Math.floor((Date.now() - aktv.mulai) / 1000);
    const box = $('logSekarang'); box.innerHTML = '';
    box.appendChild(document.createTextNode(aktv.label));
    box.appendChild(el('small', '', (aktv.model ? 'Model: ' + aktv.model + ' · ' : '') +
      (aktv.selesai ? 'proses berhenti' : d + ' dtk pada langkah ini')));
    gambarRingkas();
  }
  function gambarModel() {
    const box = $('logModel'); box.innerHTML = '';
    const nama = Object.keys(modelState);
    if (!nama.length) { box.appendChild(el('div', 'redup', '-')); return; }
    for (const n of nama) {
      const r = el('div', 'mrow'), mn = el('span', 'mn', n);
      if (peranModel[n]) mn.appendChild(el('small', '', peranModel[n]));
      r.append(el('span', 'dot ' + modelState[n]), mn, el('span', 'ms', NAMA_STATE[modelState[n]] || modelState[n]));
      box.appendChild(r);
    }
  }
  function gambarKeluaran() {
    $('logKeluaranJudul').textContent = keluaranJudul || 'Keluaran model';
    const pre = $('logKeluaran');
    pre.textContent = keluaran ? keluaran.slice(-2500) : '(belum ada keluaran)';
    pre.scrollTop = pre.scrollHeight;
  }
  function bukaPanel() {
    panelBuka = true; $('panelLog').hidden = false;
    $('logDaftar').innerHTML = '';
    for (const e of logList) gambarBarisLog(e);
    gambarSekarang(); gambarModel(); gambarKeluaran();
    $('logIsi').scrollTop = $('logIsi').scrollHeight;
    $('btnTutupLog').focus();
  }
  function tutupPanel() {
    panelBuka = false; $('panelLog').hidden = true;
    for (const e of logList) e.el = null;
  }
  $('lencanaLog').onclick = bukaPanel;
  $('btnTutupLog').onclick = tutupPanel;
  $('latarLog').onclick = tutupPanel;
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && panelBuka) tutupPanel(); });
  $('btnSalinLog').onclick = async () => {
    const teks = logList.map(e => '[' + mmss(e.t) + '] ' + e.ikon + ' ' + e.teks).join('\n');
    toast(await salinTeks(teks) ? 'Log disalin' : 'Gagal menyalin log');
  };
  setInterval(() => { if (logMulai && !aktv.selesai) renderLencana(); }, 1000);

  /* ---------- API ---------- */
  async function api(path, opt) {
    opt = Object.assign({}, opt || {});
    const h = Object.assign({'Authorization': 'Bearer ' + TOKEN}, opt.headers || {});
    if (opt.body && typeof opt.body !== 'string') { opt.body = JSON.stringify(opt.body); h['Content-Type'] = 'application/json'; }
    opt.headers = h;
    const r = await fetch(path, opt);
    if (r.status === 401) { tampil('token'); $('tokenPesan').textContent = TOKEN ? 'Token salah.' : ''; throw new Error('401'); }
    return r;
  }
  async function apij(path, opt) {
    const r = await api(path, opt);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
    return j;
  }

  /* ---------- layar ---------- */
  function ringkasCfg() {
    return cfg.mode + ' model · maks ' + cfg.maks + ' putaran';
  }
  function tampil(nama) {
    layar = nama;
    for (const n of ['token', 'setup', 'kerja']) $('layar_' + n).hidden = (n !== nama);
    $('btnPengaturan').hidden = (nama !== 'kerja');
    $('subAgent').textContent = nama === 'kerja' ? ringkasCfg() : '';
  }

  /* ---------- pengaturan ---------- */
  function muatCfg() {
    try { Object.assign(cfg, JSON.parse(localStorage.getItem('ag_cfg') || '{}')); } catch (e) { /* abaikan */ }
    cfg.mode = cfg.mode === 3 ? 3 : 2;
    cfg.maks = Math.max(1, Math.min(10, parseInt(cfg.maks, 10) || 3));
    cfg.bongkar = cfg.bongkar !== false; cfg.uji = cfg.uji !== false;
  }
  function simpanCfg() {
    try { localStorage.setItem('ag_cfg', JSON.stringify(cfg)); } catch (e) { /* abaikan */ }
  }
  function bawaanModel() {
    if (!models.length) return;
    const ada = id => models.some(m => m.id === id);
    if (!ada(cfg.p)) cfg.p = models[0].id;                                  // terkecil: cepat untuk merencana
    if (!ada(cfg.e)) cfg.e = models[models.length - 1].id;                  // terbesar: menulis kode
    if (!ada(cfg.c)) cfg.c = models[Math.floor(models.length / 2)].id;
    if (cfg.p === cfg.e && models.length > 1) cfg.e = models.find(m => m.id !== cfg.p).id;
  }
  function isiPilihan(sel, nilai) {
    sel.innerHTML = '';
    for (const m of models) {
      const o = document.createElement('option'); o.value = m.id;
      o.textContent = m.id + ' · ' + gb(m.mb);
      sel.appendChild(o);
    }
    if (models.some(m => m.id === nilai)) sel.value = nilai;
  }
  function renderSetup(paksaDaftar) {
    for (const b of document.querySelectorAll('#segMode button')) {
      const on = Number(b.dataset.mode) === cfg.mode;
      b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    $('fieldC').hidden = cfg.mode !== 3;
    $('namaP').textContent = cfg.mode === 3 ? 'Model 1 · Perencana' : 'Model 1 · Perencana + Pemeriksa';
    $('ketP').textContent = cfg.mode === 3
      ? 'Menerima perintah, menyusun lembar tugas, lalu menjelaskan hasil akhir.'
      : 'Menerima perintah, menyusun lembar tugas, memeriksa hasil, dan menjelaskannya.';
    $('ketMode').textContent = cfg.mode === 3
      ? 'Tiap peran punya model sendiri. Model yang sama boleh dipilih untuk dua peran.'
      : 'Model 1 merencana dan memeriksa, Model 2 menulis program.';
    const sig = models.map(m => m.id).join('|');
    if (paksaDaftar || sig !== daftarSig) {   // jangan bangun ulang pilihan saat polling (menutup menu di HP)
      daftarSig = sig;
      isiPilihan($('selP'), cfg.p); isiPilihan($('selE'), cfg.e); isiPilihan($('selC'), cfg.c);
    }
    $('inpMaks').value = cfg.maks;
    $('cbBongkar').checked = cfg.bongkar; $('cbUji').checked = cfg.uji;
    cekSetup();
  }
  function cekSetup() {
    const pilih = cfg.mode === 3 ? [cfg.p, cfg.e, cfg.c] : [cfg.p, cfg.e];
    const unik = Array.from(new Set(pilih));
    let pesan = '', ok = true;
    if (models.length < 2) { pesan = 'Butuh minimal 2 model di llama-server.'; ok = false; }
    else if (unik.length < 2) { pesan = 'Pilih minimal 2 model yang berbeda.'; ok = false; }
    if (statusSrv && statusSrv.chat_aktif) {
      pesan = 'Sesi chat masih memegang model' + (statusSrv.model_chat ? ' (' + statusSrv.model_chat + ')' : '') +
        '. Akhiri dulu di halaman Chat (tombol Selesai).';
      ok = false;
    } else if (statusSrv && statusSrv.sibuk) { pesan = 'Masih ada proses berjalan di server.'; ok = false; }
    else if (statusSrv && statusSrv.pesan && !models.length) { pesan = statusSrv.pesan; ok = false; }
    $('setupPesan').className = ok ? '' : 'err'; $('setupPesan').textContent = pesan;
    $('btnMulai').disabled = !ok;
    const mb = unik.map(id => (models.find(m => m.id === id) || {}).mb || 0);
    const perlu = cfg.bongkar ? Math.max.apply(null, mb.concat([0])) : mb.reduce((a, b) => a + b, 0);
    $('ketMemori').textContent = perlu
      ? 'Memori model yang dibutuhkan sekaligus: sekitar ' + gb(perlu) + (cfg.bongkar ? ' (satu model per tahap)' : ' (semua model tetap termuat)') + ', belum termasuk konteks.'
      : '';
  }
  async function muatStatus(paksa) {
    try {
      statusSrv = await apij('/api/agent/status');
      models = statusSrv.models || [];
      bawaanModel();
      renderSetup(!!paksa);
    } catch (e) {
      if (e.message !== '401') { $('setupPesan').className = 'err'; $('setupPesan').textContent = 'Tidak bisa terhubung ke server.'; }
    }
  }
  function ubahMaks(n) {
    cfg.maks = Math.max(1, Math.min(10, parseInt(n, 10) || cfg.maks));
    $('inpMaks').value = cfg.maks; simpanCfg();
  }
  for (const b of document.querySelectorAll('#segMode button')) {
    b.onclick = () => { cfg.mode = Number(b.dataset.mode) === 3 ? 3 : 2; simpanCfg(); renderSetup(false); };
  }
  $('selP').onchange = e => { cfg.p = e.target.value; simpanCfg(); cekSetup(); };
  $('selE').onchange = e => { cfg.e = e.target.value; simpanCfg(); cekSetup(); };
  $('selC').onchange = e => { cfg.c = e.target.value; simpanCfg(); cekSetup(); };
  $('btnKurang').onclick = () => ubahMaks(cfg.maks - 1);
  $('btnTambah').onclick = () => ubahMaks(cfg.maks + 1);
  $('inpMaks').addEventListener('change', e => ubahMaks(e.target.value));
  $('cbBongkar').onchange = e => { cfg.bongkar = e.target.checked; simpanCfg(); cekSetup(); };
  $('cbUji').onchange = e => { cfg.uji = e.target.checked; simpanCfg(); };
  $('btnMuatUlang').onclick = async () => {
    const b = $('btnMuatUlang'); b.disabled = true;
    try { await apij('/api/model/muat-ulang', {method: 'POST', body: {}}); } catch (e) { if (e.message !== '401') toast(e.message); }
    b.disabled = false; muatStatus(true);
  };
  $('btnMulai').onclick = () => {
    $('input').value = ''; ukuranInput(); masukKerja();
  };
  $('btnPengaturan').onclick = () => {
    if (sibuk) { toast('Tunggu proses selesai atau tekan Stop.'); return; }
    tampil('setup'); muatStatus(true); muatRiwayat();
  };

  /* ---------- riwayat ---------- */
  const LABEL_STATUS = {lolos: '✔ lolos', belum: '⚠ belum sempurna', butuh_info: '❓ butuh info', batal: 'dibatalkan', error: '✖ error'};
  const BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
  function waktuRingkas(iso) {   // 2026-10-19T00:35:05 -> "19 Okt · 00:35"
    const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso || '');
    return m ? parseInt(m[3], 10) + ' ' + BULAN[parseInt(m[2], 10) - 1] + ' · ' + m[4] + ':' + m[5] : (iso || '');
  }
  let riwayat = [];
  async function muatRiwayat() {
    try { riwayat = (await apij('/api/agent/riwayat')).run || []; } catch (e) { return; }
    gambarRiwayat();
  }
  function gambarRiwayat() {
    const box = $('daftarRun'); box.innerHTML = '';
    $('btnHapusRiwayat').hidden = !riwayat.length;
    if (!riwayat.length) { box.appendChild(el('p', 'redup kosong', 'Belum ada riwayat Agent.')); return; }
    for (const r of riwayat) {
      const baris = el('div', 'baris-run');
      const b = el('button', 'model st-' + (r.status || '')); b.type = 'button';
      b.append(el('span', 'nama', r.judul || r.id),
        el('span', 'meta', waktuRingkas(r.dibuat) + ' · ' + (LABEL_STATUS[r.status] || r.status || '').replace(/^\S+\s/, '') +
          (r.putaran ? ' · putaran ' + r.putaran + '/' + r.maks : '')));
      b.onclick = () => bukaRun(r.id);
      const x = el('button', 'x', '✕'); x.type = 'button'; x.setAttribute('aria-label', 'Hapus proses ini');
      x.onclick = () => hapusRun(r);
      baris.append(b, x); box.appendChild(baris);
    }
  }
  async function hapusRun(r) {
    if (!confirm('Hapus proses "' + (r.judul || r.id) + '"? Berkas hasil program di folder prosesnya ikut terhapus dan tidak bisa dikembalikan.')) return;
    try { await apij('/api/agent/run/' + r.id, {method: 'DELETE'}); }
    catch (e) { if (e.message !== '401') toast(e.message); return; }
    if (lanjutId === r.id) aturLanjut(null, '');
    toast('Proses dihapus');
    muatRiwayat();
  }
  async function hapusSemuaRiwayat() {
    if (!riwayat.length) { toast('Tidak ada riwayat untuk dihapus.'); return; }
    if (!confirm('Hapus ' + riwayat.length + ' proses Agent beserta semua berkas hasilnya? Tidak bisa dikembalikan.')) return;
    try {
      const j = await apij('/api/agent/riwayat/hapus-semua', {method: 'POST', body: {}});
      toast(j.dihapus + ' proses dihapus');
      aturLanjut(null, '');
    } catch (e) { if (e.message !== '401') toast(e.message); }
    muatRiwayat();
  }
  $('btnHapusRiwayat').onclick = hapusSemuaRiwayat;
  async function bukaRun(id) {
    let r;
    try { r = await apij('/api/agent/run/' + id); } catch (e) { if (e.message !== '401') toast(e.message); return; }
    masukKerja(true);
    tambahUser(r.tugas || '');
    if (r.spec) kartuRencana(r.spec);
    for (const b of (r.berkas || [])) kartuBerkas(b.nama, b.isi, false, false);
    if (r.laporan) { const st2 = {raw: r.laporan, bubble: tambahAsisten(''), kartuLaporan: null}; isiLaporan(st2); }
    tambahHasil({status: r.status, teks: LABEL_STATUS[r.status] || r.status, dir: r.dir});
    aturLanjut(r.id, r.judul);
    gulir(true);
  }

  /* ---------- layar kerja ---------- */
  function masukKerja(tanpaSapaan) {
    tampil('kerja'); resetLog();
    $('pesan').innerHTML = ''; resetAlur(); $('infoAlur').textContent = '';
    aturLanjut(null, '');
    if (!tanpaSapaan) kartuTim();
  }
  function kartuTim() {
    const model = cfg.mode === 3 ? [cfg.p, cfg.e, cfg.c] : [cfg.p, cfg.e, cfg.p];
    const baris = [['rencana', '🧭', 'Perencana', model[0], 'menyusun lembar tugas, lalu menjelaskan hasil'],
      ['tulis', '✏️', 'Pelaksana', model[1], 'menulis program'],
      ['periksa', '🔎', 'Pemeriksa', model[2], 'memeriksa dan memberi koreksi']];
    const k = el('div', 'kartu tim');
    k.appendChild(el('b', 'jdl', 'Tim siap · maks ' + cfg.maks + ' putaran'));
    for (const [kunci, ik, nama, mdl, tugas] of baris) {
      const r = el('div', 'baris-tim r-' + kunci), rt = el('span', 'rt');
      rt.append(el('b', '', nama + ' · ' + mdl), el('small', '', tugas));
      r.append(el('span', 'rk', ik), rt); k.appendChild(r);
    }
    k.appendChild(el('div', 'redup kecil', 'Tulis apa yang ingin dibuat.'));
    $('pesan').appendChild(k);
  }
  function aturLanjut(id, judul) {
    lanjutId = id || null; lanjutJudul = judul || ''; awalTanya = null;
    $('lanjutBar').hidden = !lanjutId;
    $('lanjutTeks').textContent = lanjutId ? 'Melanjutkan proyek: ' + lanjutJudul : '';
    $('input').placeholder = lanjutId ? 'Minta perbaikan atau tambahan...' : 'Apa yang ingin dibuat?';
  }
  $('btnBaru').onclick = () => { if (sibuk) { toast('Tunggu proses selesai atau tekan Stop.'); return; } aturLanjut(null, ''); };

  const URUT = ['rencana', 'tulis', 'periksa', 'jelaskan'];
  const PERAN = {rencana: 'Perencana', tulis: 'Pelaksana', periksa: 'Pemeriksa', jelaskan: 'Penjelas'};
  const IKON = {rencana: '🧭', tulis: '✏', periksa: '🔎', jelaskan: '💬'};
  let selesaiSet = new Set(), aktifKunci = null;
  let alurTutup = false;
  function gambarAlur(kunci, putaran) {
    let terjauh = -1;
    URUT.forEach((k, i) => { if (selesaiSet.has(k)) terjauh = i; });
    URUT.forEach((k, i) => {
      const c = $('st_' + k), akt = (k === kunci), sel = !akt && selesaiSet.has(k);
      const lewat = alurTutup && !akt && !sel && i < terjauh;      // mis. Pemeriksa dilewati
      c.className = 'lk' + (akt ? ' aktif' : sel ? ' selesai' : lewat ? ' lewat' : '');
      c.querySelector('.bl').textContent = sel ? '✓' : lewat ? '–' : String(i + 1);
      c.querySelector('.nm').textContent = PERAN[k] +
        ((akt && putaran && (k === 'tulis' || k === 'periksa')) ? ' · ' + putaran : '');
    });
  }
  function resetAlur() {
    selesaiSet = new Set(); aktifKunci = null; alurTutup = false; gambarAlur(null, 0);
  }
  function setAlur(kunci, putaran) {
    if (aktifKunci) selesaiSet.add(aktifKunci);
    aktifKunci = kunci; gambarAlur(kunci, putaran);
  }
  function akhiriAlur() {
    if (aktifKunci) selesaiSet.add(aktifKunci);
    aktifKunci = null; alurTutup = true; gambarAlur(null, 0);
  }

  /* ---------- render pesan ---------- */
  function tambahUser(teks) {
    const p = el('div', 'p user'), g = el('div', 'gel', teks);
    p.appendChild(g); $('pesan').appendChild(p); gulir(true);
  }
  function tambahAsisten(teks) {
    const p = el('div', 'p'), g = el('div', 'gel'); g.innerHTML = md(teks);
    p.appendChild(g); $('pesan').appendChild(p); gulir();
    return g;
  }
  function tambahInfo(teks, err) {
    $('pesan').appendChild(el('div', 'info' + (err ? ' err' : ''), teks)); gulir();
  }
  function lencana(kelas, teks) { return el('span', 'lencana ' + kelas, teks); }
  function daftarUl(arr) {
    const ul = el('ul');
    for (const x of arr) ul.appendChild(el('li', '', x));
    return ul;
  }
  function kartuRencana(spec) {
    const k = el('div', 'kartu rencana');
    k.appendChild(el('b', 'jdl', '📋 ' + (spec.judul || 'Lembar tugas')));
    if (spec.ringkasan) k.appendChild(el('div', '', spec.ringkasan));
    k.appendChild(el('div', 'sub', 'Berkas'));
    for (const b of (spec.berkas || [])) {
      const r = el('div', 'bk');
      r.appendChild(el('span', 'pb', b.nama));
      if (b.fungsi) r.appendChild(el('span', 'fg', b.fungsi));
      k.appendChild(r);
    }
    if ((spec.kriteria || []).length) { k.appendChild(el('div', 'sub', 'Kriteria selesai')); k.appendChild(daftarUl(spec.kriteria)); }
    k.appendChild(el('div', 'uji', '▶ ' + ((spec.jalankan || []).length ? spec.jalankan.join(' ') : 'tanpa uji jalan')));
    if ((spec.harapan || []).length) k.appendChild(el('div', 'uji', '🎯 harapan keluaran: ' + spec.harapan.join(', ')));
    if (spec.catatan) k.appendChild(el('div', 'uji', 'Catatan: ' + spec.catatan));
    $('pesan').appendChild(k); gulir();
  }
  function kartuBerkas(nama, isi, baru, dipotong) {
    const d = el('details', 'tool berkas'), s = el('summary');
    const baris = isi.replace(/\n$/, '').split('\n').length;
    const rg = el('span', 'rg', nama);
    rg.appendChild(el('small', '', baris + ' baris'));
    const ext = nama.indexOf('.') >= 0 ? nama.split('.').pop().slice(0, 5) : '';
    s.append(el('span', 'ik', '📄'), rg);
    if (ext) s.appendChild(el('span', 'bhs', ext));
    s.appendChild(lencana(baru ? 'ok' : 'menunggu', baru ? 'baru' : 'diubah'));
    const kotak = el('div', 'kode'), salin = el('button', 'salin', 'Salin'); salin.type = 'button';
    const pre = el('pre'); pre.textContent = isi + (dipotong ? '\n...[tampilan dipotong; isi lengkap ada di folder hasil]' : '');
    kotak._teks = isi;
    kotak.append(salin, pre); d.append(s, kotak); $('pesan').appendChild(d); gulir();
  }
  function kartuCek(ev) {
    const d = el('details', 'tool'), s = el('summary');
    s.append(el('span', 'ik', '🔧'), el('span', 'rg', 'Pemeriksaan otomatis' + (ev.jalan && ev.jalan !== 'dilewati' ? ' · uji jalan ' + ev.jalan : '')),
      lencana(ev.ok ? 'ok' : 'gagal', ev.ok ? 'lolos' : 'gagal'));
    const pre = el('pre'); pre.textContent = ev.d;
    d.append(s, pre); if (!ev.ok) d.open = true;
    $('pesan').appendChild(d); gulir();
  }
  function kartuNilai(ev) {
    const k = el('div', 'kartu nilai ' + (ev.ok ? 'ok' : 'gagal'));
    const b = el('div', 'baris'); b.append(lencana(ev.ok ? 'ok' : 'ditolak', ev.ok ? 'Pemeriksa: OK' : 'Pemeriksa: perlu perbaikan'));
    k.appendChild(b);
    if (ev.ringkas) k.appendChild(el('div', '', ev.ringkas));
    if ((ev.masalah || []).length) { k.appendChild(el('div', 'sub', 'Masalah')); k.appendChild(daftarUl(ev.masalah)); }
    if (ev.perbaikan && !ev.ok) k.appendChild(el('div', 'sub', 'Perbaikan: ' + ev.perbaikan));
    $('pesan').appendChild(k); gulir();
  }
  const IKON_STATUS = {lolos: '✔', belum: '⚠', butuh_info: '❓', batal: '⏹', error: '✖'};
  function tambahHasil(ev) {
    const d = el('div', 'hasil ' + (ev.status || '')), tx = el('div', 'hs-tx');
    const t = String(ev.teks || ev.status || '');
    tx.appendChild(el('b', '', t.charAt(0).toUpperCase() + t.slice(1)));
    if (ev.dir) tx.appendChild(el('small', '', ev.dir));
    d.append(el('span', 'hs-ik', IKON_STATUS[ev.status] || '•'), tx);
    $('pesan').appendChild(d); gulir();
  }
  /* laporan akhir: prosa dari Penjelas (gelembung) + fakta dari sistem (kartu berbaris) */
  const POLA_FAKTA = /\n\n(?=\S{1,3} \*\*Status\*\*)/;
  const KELAS_IKON = {'✔': 'lolos', '⚠': 'belum', '⏹': 'batal', '✖': 'error'};
  function barisLaporan(teks) {
    const rows = []; let cur = null, pagar = false;
    for (const baris of teks.split('\n')) {
      const m = pagar ? null : /^(?:(\S{1,3}) )?\*\*(.+?)\*\*:\s?(.*)$/.exec(baris);
      if (m) { cur = {ik: m[1] || '', k: m[2], v: m[3], kode: null}; rows.push(cur); continue; }
      if (!cur) continue;
      if (/^```/.test(baris)) { pagar = !pagar; if (pagar && cur.kode === null) cur.kode = ''; continue; }
      if (pagar) cur.kode += (cur.kode ? '\n' : '') + baris;
      else if (baris.trim()) cur.v += (cur.v ? ' ' : '') + baris.trim();
    }
    return rows;
  }
  function gambarKartuLaporan(kartu, rows) {
    kartu.innerHTML = '';
    rows.forEach((r, i) => {
      const d = el('div', 'lp' + (i === 0 ? ' utama' : '')), k = el('div', 'k', r.k), v = el('div', 'v');
      v.innerHTML = md(r.ik && i === 0 ? r.ik + ' ' + r.v : r.v);
      if (r.kode !== null) {
        const kotak = el('div', 'kode'), salin = el('button', 'salin', 'Salin'), pre = el('pre');
        salin.type = 'button'; pre.textContent = r.kode; kotak._teks = r.kode;
        kotak.append(salin, pre); v.appendChild(kotak);
      }
      d.append(k, v); kartu.appendChild(d);
    });
  }
  function isiLaporan(st) {
    const i = st.raw.search(POLA_FAKTA);
    const prosa = (i >= 0 ? st.raw.slice(0, i) : st.raw).trim();
    st.bubble.innerHTML = md(prosa);
    if (st.bubble.parentElement) st.bubble.parentElement.hidden = !prosa;
    if (i < 0) return;
    if (!st.kartuLaporan) { st.kartuLaporan = el('div', 'laporan'); $('pesan').appendChild(st.kartuLaporan); }
    const rows = barisLaporan(st.raw.slice(i).trim());
    st.kartuLaporan.className = 'laporan ' + (KELAS_IKON[rows.length ? rows[0].ik : ''] || '');
    gambarKartuLaporan(st.kartuLaporan, rows);
  }
  function kartuKonfirmasi(ev) {
    const d = el('div', 'konf');
    const t = el('b', '', ({uji: 'Izinkan menjalankan program hasil agent?', tulis: 'Izinkan menulis file?',
      jaringan: 'Izinkan akses jaringan?'})[ev.jenis] || 'Izinkan menjalankan perintah?');
    const pre = el('pre'); pre.textContent = ev.ringkas + (ev.detail ? '\n\n' + ev.detail : '');
    const row = el('div', 'baris');
    const ya = el('button', 'btn', 'Ya, izinkan'), tidak = el('button', 'btn abu', 'Tolak');
    const jawab = async setuju => {
      ya.disabled = true; tidak.disabled = true;
      try {
        await apij('/api/konfirmasi', {method: 'POST', body: {kid: ev.kid, setuju}});
        row.textContent = setuju ? '✔ Diizinkan' : '✖ Ditolak';
        catatLog(setuju ? '✔' : '✖', setuju ? 'Izin diberikan' : 'Izin ditolak', setuju ? 'ok' : 'izin');
        if (ev.jenis === 'uji') setAktif(setuju ? 'Menjalankan program uji' : 'Pemeriksaan otomatis', '');
        else setAktif('Melanjutkan proses', '');
      } catch (e) { row.textContent = 'Gagal: ' + e.message; }
    };
    ya.onclick = () => jawab(true); tidak.onclick = () => jawab(false);
    row.append(ya, tidak); d.append(t, pre, row); $('pesan').appendChild(d); gulir(true);
  }
  function teksInfo(ev) {
    let t = ev.tok + ' token · ' + ev.tok_s + ' tok/s';
    if (ev.pakai && ev.maks) {
      const pct = Math.min(100, Math.round(ev.pakai / ev.maks * 100));
      t += ' · konteks ' + ribu(ev.pakai) + '/' + ribu(ev.maks) + ' (' + pct + '%)' + (pct >= 85 ? ' ⚠ hampir penuh' : '');
    }
    return t;
  }

  /* kartu tahap: satu kartu per tahap, berisi status muat model dan keluaran model */
  function kartuTahap(ev, st) {
    tutupKartu(st, 'ok', 'selesai');
    const d = el('details', 'tool tahap r-' + ev.tahap), s = el('summary');
    const lc = lencana('menunggu', 'berjalan');
    const rg = el('span', 'rg');
    rg.append(el('b', '', ev.peran + (ev.putaran ? ' · putaran ' + ev.putaran : '')), el('small', '', ev.model));
    s.append(el('span', 'ik', IKON[ev.tahap] || '⚙'), rg, lc);
    const stat = el('div', 'stat', 'Menyiapkan model ...'), pre = el('pre');
    d.append(s, stat, pre); d.open = true; $('pesan').appendChild(d);
    st.kartu = {d, lc, stat, pre, raw: ''}; gulir();
  }
  function tutupKartu(st, kelas, label) {
    const k = st.kartu; if (!k) return;
    k.lc.className = 'lencana ' + kelas; k.lc.textContent = label;
    k.d.open = false; st.kartu = null;
  }

  /* ---------- kirim & stream ---------- */
  function setSibuk(v) {
    sibuk = v;
    $('btnKirim').textContent = v ? '■' : '↑';
    $('btnKirim').setAttribute('aria-label', v ? 'Stop' : 'Kirim');
    $('btnKirim').className = v ? 'btn merah' : 'btn';
  }
  function ukuranInput() {
    const i = $('input'); i.style.height = 'auto'; i.style.height = Math.min(i.scrollHeight, 160) + 'px';
  }
  async function kirim() {
    const diketik = $('input').value.trim();
    if (!diketik || sibuk) return;
    let teks = diketik;
    if (awalTanya) {   // jawaban atas pertanyaan Perencana: gabungkan dengan permintaan awal
      teks = 'Permintaan awal: ' + awalTanya + '\nJawaban/tambahan pengguna: ' + diketik;
    }
    $('input').value = ''; ukuranInput();
    tambahUser(diketik); setSibuk(true); resetAlur(); $('infoAlur').textContent = 'Menghubungi server ...';
    mulaiLog(diketik);
    const st = {kartu: null, bubble: null, raw: '', teks};
    try {
      const body = {teks, lanjut: lanjutId, mode: cfg.mode, model_p: cfg.p, model_e: cfg.e,
        model_c: cfg.mode === 3 ? cfg.c : cfg.p, maks: cfg.maks, bongkar: cfg.bongkar, uji: cfg.uji};
      const r = await api('/api/agent/jalankan', {method: 'POST', body});
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || ('HTTP ' + r.status)); }
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      while (true) {
        const {value, done} = await rd.read(); if (done) break;
        buf += dec.decode(value, {stream: true});
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
          const baris = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
          if (!baris) continue;
          let ev; try { ev = JSON.parse(baris); } catch (e) { continue; }
          tangani(ev, st);
        }
      }
    } catch (e) {
      if (e.message !== '401') {
        tambahInfo('⚠ ' + e.message, true); $('infoAlur').textContent = '';
        catatLog('✖', 'Terputus: ' + e.message, 'gagal');
      }
    } finally {
      tutupKartu(st, 'gagal', 'berhenti'); akhiriAlur(); setSibuk(false); muatRiwayat();
      if (logMulai && !aktv.selesai) akhiriLog('Terputus dari server', true);
    }
  }
  const KATA_AKTIF = {rencana: 'menyusun lembar tugas', tulis: 'menulis kode', periksa: 'menilai hasil',
    jelaskan: 'menjelaskan hasil'};
  function mulaiMenulis(st) {   // token pertama tiba: model sudah termuat dan mulai menjawab
    if (st.menulis || !st.tahap) return;
    st.menulis = true;
    const t = st.tahap, kata = KATA_AKTIF[t.tahap] || 'menulis';
    setModel(t.model, 'termuat');
    setAktif(t.peran + ' ' + kata, t.model);
    catatLog('✍', t.peran + ' mulai ' + kata);
  }
  function tambahKeluaran(d) {
    keluaran += d;
    if (keluaran.length > 6000) keluaran = keluaran.slice(-4000);
    if (panelBuka) gambarKeluaran();
  }
  const LABEL_AKHIR = {lolos: 'Selesai · lolos pemeriksaan', belum: 'Selesai · belum sempurna',
    butuh_info: 'Menunggu infomu', batal: 'Dibatalkan', error: 'Berhenti karena error'};
  function tangani(ev, st) {
    switch (ev.t) {
      case 'mulai':
        $('infoAlur').textContent = 'Folder kerja: ' + ev.dir;
        catatLog('📁', 'Folder kerja: ' + ev.dir); break;
      case 'tahap':
        kartuTahap(ev, st); setAlur(ev.tahap, ev.putaran);
        st.tahap = ev; st.menulis = false; keluaran = ''; keluaranJudul = 'Keluaran ' + ev.peran + ' · ' + ev.model;
        if (panelBuka) gambarKeluaran();
        catatLog('▶', 'Tahap ' + ev.peran + (ev.putaran ? ' (putaran ' + ev.putaran + ')' : '') + ' · model ' + ev.model, 'tahap');
        setAktif(ev.peran + ' berpikir', ev.model); break;
      case 'putaran':
        $('infoAlur').textContent = 'Putaran ' + ev.n + ' dari maks ' + ev.maks;
        tambahInfo('🔁 Putaran ' + ev.n + '/' + ev.maks);
        catatLog('🔁', 'Putaran ' + ev.n + ' dari maksimal ' + ev.maks, 'tahap'); break;
      case 'muat':
        if (st.kartu) st.kartu.stat.textContent = ev.d;
        $('infoAlur').textContent = ev.d;
        setModel(ev.model, 'memuat'); setAktif('Memuat model', ev.model);
        if (!st.muat || st.muat.model !== ev.model) st.muat = {model: ev.model, e: catatLog('⏳', ev.d)};
        else ubahLog(st.muat.e, ev.d);
        break;
      case 'muat_selesai':
        if (st.kartu) st.kartu.stat.textContent = '✔ Model siap (' + ev.detik + ' dtk)';
        $('infoAlur').textContent = '';
        setModel(ev.model, 'termuat'); st.muat = null;
        catatLog('✔', ev.model + ' siap dipakai (' + ev.detik + ' dtk)', 'ok');
        setAktif((st.tahap ? st.tahap.peran : 'Model') + ' berpikir', ev.model); break;
      case 'bongkar_mulai':
        setModel(ev.model, 'membongkar'); setAktif('Membongkar model', ev.model);
        catatLog('⏏', 'Membongkar ' + ev.model + ' dari memori ...'); break;
      case 'bongkar':
        tambahInfo('⏏ ' + ev.model + ' dibongkar dari memori');
        setModel(ev.model, 'dibongkar'); catatLog('✔', ev.model + ' sudah dibongkar', 'ok');
        setAktif('Beralih ke tahap berikutnya', ''); break;
      case 'isi':
        mulaiMenulis(st); tambahKeluaran(ev.d);
        if (st.kartu) { st.kartu.raw += ev.d; st.kartu.pre.textContent = st.kartu.raw; st.kartu.pre.scrollTop = st.kartu.pre.scrollHeight; }
        break;
      case 'info':
        tambahInfo(teksInfo(ev), false); catatLog('📊', teksInfo(ev)); break;
      case 'rencana':
        st.judul = ev.d.judul; tutupKartu(st, 'ok', 'selesai'); kartuRencana(ev.d);
        catatLog('📋', 'Lembar tugas: ' + ev.d.judul + ' (' + (ev.d.berkas || []).length + ' berkas)'); break;
      case 'berkas':
        kartuBerkas(ev.nama, ev.isi, ev.baru, ev.dipotong);
        catatLog('✏', (ev.baru ? 'Membuat ' : 'Mengubah ') + ev.nama); break;
      case 'cek_mulai':
        setAktif('Pemeriksaan otomatis', '');
        catatLog('🔧', 'Pemeriksaan otomatis: berkas dan sintaks'); break;
      case 'uji_mulai':
        setAktif('Menjalankan program uji', '');
        catatLog('▶', 'Menjalankan uji: ' + ev.d); break;
      case 'cek': {
        kartuCek(ev);
        const jalan = (ev.jalan === 'lolos' || ev.jalan === 'gagal') ? ' · uji jalan ' + ev.jalan : '';
        const harap = ev.harapan === true ? ' · sesuai harapan Perencana' : '';
        catatLog(ev.ok ? '✔' : '✖', 'Pemeriksaan otomatis ' + (ev.ok ? 'lolos' : 'gagal') + jalan + harap, ev.ok ? 'ok' : 'gagal');
        for (const b of ev.d.split('\n').filter(x => x.indexOf('GAGAL') === 0).slice(0, 3)) catatLog('', b.slice(0, 160), 'sub gagal');
        break;
      }
      case 'nilai':
        tutupKartu(st, ev.ok ? 'ok' : 'ditolak', ev.ok ? 'OK' : 'perlu perbaikan'); kartuNilai(ev);
        catatLog(ev.ok ? '✔' : '✖', 'Pemeriksa: ' + (ev.ok ? 'OK' : 'perlu perbaikan') + (ev.ringkas ? ' - ' + ev.ringkas : ''), ev.ok ? 'ok' : 'izin');
        for (const m of (ev.masalah || []).slice(0, 3)) catatLog('', m.slice(0, 160), 'sub');
        break;
      case 'token':     // penjelasan akhir dari Perencana
        mulaiMenulis(st); tambahKeluaran(ev.d);
        if (!st.bubble) { tutupKartu(st, 'ok', 'selesai'); st.bubble = tambahAsisten(''); st.raw = ''; }
        st.raw += ev.d; isiLaporan(st); gulir(); break;
      case 'tanya':
        tutupKartu(st, 'ok', 'selesai'); tambahAsisten(ev.d); awalTanya = st.teks;
        catatLog('❓', 'Perencana bertanya: ' + ev.d.slice(0, 120), 'izin'); break;
      case 'ringkas':
        tambahInfo('ℹ ' + ev.d); catatLog('ℹ', ev.d); break;
      case 'pulih':
        tambahInfo('↩ ' + ev.d); catatLog('↩', ev.d, 'izin'); break;
      case 'konfirmasi':
        kartuKonfirmasi(ev); setAktif('Menunggu izinmu', '', true);
        catatLog('❓', 'Meminta izin: ' + ev.ringkas.slice(0, 120), 'izin'); break;
      case 'error':
        tutupKartu(st, 'gagal', 'error'); tambahInfo('⚠ ' + ev.d, true); catatLog('✖', ev.d, 'gagal'); break;
      case 'batal':
        tutupKartu(st, 'ditolak', 'dibatalkan'); tambahInfo('Dibatalkan.'); catatLog('⏹', 'Dibatalkan', 'izin'); break;
      case 'selesai':
        tutupKartu(st, 'ok', 'selesai'); akhiriAlur(); $('infoAlur').textContent = '';
        tambahHasil(ev);
        catatLog(IKON_STATUS[ev.status] || '•', 'Selesai: ' + ev.teks, ev.status === 'lolos' ? 'ok' : (ev.status === 'error' ? 'gagal' : 'izin'));
        akhiriLog(LABEL_AKHIR[ev.status] || 'Selesai', ev.status === 'error');
        if (ev.status === 'lolos' || ev.status === 'belum') { aturLanjut(ev.id, st.judul || (st.teks || '').slice(0, 40)); }
        st.bubble = null; st.kartuLaporan = null; break;
      default: break;   // ping
    }
  }

  /* ---------- event ---------- */
  $('bawah').addEventListener('submit', e => {
    e.preventDefault();
    if (sibuk) {
      catatLog('⏹', 'Stop ditekan, menghentikan proses ...', 'izin'); setAktif('Menghentikan proses', aktv.model, true);
      api('/api/stop', {method: 'POST', body: {}}).catch(() => {});
    } else kirim();
  });
  $('input').addEventListener('input', ukuranInput);
  $('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!sibuk) kirim(); }
  });
  $('pesan').addEventListener('click', async e => {   // tombol Salin (blok kode & berkas)
    const b = e.target.closest('.salin'); if (!b) return;
    const kotak = b.parentElement, pre = kotak.querySelector('pre'); if (!pre) return;
    const ok = await salinTeks(kotak._teks !== undefined ? kotak._teks : pre.textContent);
    b.textContent = ok ? 'Tersalin ✓' : 'Gagal menyalin';
    setTimeout(() => { b.textContent = 'Salin'; }, 1500);
  });
  $('btnToken').onclick = () => {
    const v = $('tokenInput').value.trim(); if (!v) return;
    TOKEN = v; localStorage.setItem('aa_token', v); $('tokenPesan').textContent = '';
    tampil('setup'); muatStatus(true); muatRiwayat();
  };
  $('tokenInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('btnToken').click(); });
  setInterval(() => { if (layar === 'setup' && !document.hidden && TOKEN) muatStatus(false); }, 6000);

  /* ---------- mulai ---------- */
  muatCfg();
  const qs = new URLSearchParams(location.search);
  if (qs.get('token')) {
    TOKEN = qs.get('token'); localStorage.setItem('aa_token', TOKEN);
    history.replaceState(null, '', location.pathname);
  }
  if (!TOKEN) tampil('token');
  else { tampil('setup'); muatStatus(true); muatRiwayat(); }
})();
