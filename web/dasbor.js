(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  let TOKEN = localStorage.getItem('aa_token') || '';
  let layar = '', timer = null, memuat = false;

  const NAMA_SKILL = {tanpa: 'Tanpa skill', web: 'Web', dasar: 'Dasar', kompleks: 'Kompleks', kritis: 'Berpikir kritis'};
  const STATUS_RUN = {
    berjalan: ['Berjalan', 'menunggu'], terhenti: ['Terhenti', 'ditolak'], lolos: ['Lolos', 'ok'],
    analisis: ['Analisis', 'menunggu'], belum: ['Belum sempurna', 'ditolak'], butuh_info: ['Butuh info', 'ditolak'],
    batal: ['Dibatalkan', ''], error: ['Error', 'gagal'],
  };
  const BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];

  /* ---------- util ---------- */
  function el(tag, kelas, teks) {
    const e = document.createElement(tag);
    if (kelas) e.className = kelas;
    if (teks !== undefined) e.textContent = teks;
    return e;
  }
  function potong(s, n) {
    s = String(s || '').replace(/\s+/g, ' ').trim();
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }
  function waktuRingkas(iso) {      // 2026-10-19T00:35:05 -> "19 Okt · 00:35"
    const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso || '');
    return m ? parseInt(m[3], 10) + ' ' + BULAN[parseInt(m[2], 10) - 1] + ' · ' + m[4] + ':' + m[5] : (iso || '');
  }
  function salam() {
    const j = new Date().getHours();
    return j < 4 ? 'Selamat malam' : j < 11 ? 'Selamat pagi' : j < 15 ? 'Selamat siang' : j < 19 ? 'Selamat sore' : 'Selamat malam';
  }
  function labelSkill(sk) {
    return (sk || []).map(x => NAMA_SKILL[x] || x).join(' + ');
  }
  let toastT = null;
  function toast(m) {
    const t = $('toast'); t.textContent = m; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 3500);
  }
  function tampil(nama) {
    layar = nama;
    for (const n of ['token', 'dasbor']) $('layar_' + n).hidden = (n !== nama);
    if (nama === 'dasbor') $('salam').textContent = salam();
  }

  /* ---------- API ---------- */
  async function api(path) {
    const r = await fetch(path, {headers: {'Authorization': 'Bearer ' + TOKEN}});
    if (r.status === 401) {
      tampil('token');
      $('tokenPesan').textContent = TOKEN ? 'Token salah.' : '';
      throw new Error('401');
    }
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  /* ---------- gambar ---------- */
  function setStatus(id, st, teks) {
    const box = $(id);
    box.dataset.st = st;
    box.querySelector('span').textContent = teks;
  }
  function chip(st, teks) {
    $('chipServer').dataset.st = st;
    $('chipTeks').textContent = teks;
  }
  function baris(label, st, teks) {
    const k = el('div', 'k');
    k.append(el('dt', '', label));
    const dd = el('dd');
    dd.dataset.st = st;
    dd.append(el('i', 'titik-st'), el('span', '', teks));
    k.append(dd);
    return k;
  }
  function gambar(s, chats, runs) {
    const utama = ((s.koneksi || {}).daftar || []).find(k => k.utama) || null;
    const ag = (s.agent && s.agent.aktif) ? s.agent : null;
    const nChat = Array.isArray(chats) ? chats.length : null;

    // chip di header
    if (utama && utama.ok === false) chip('peringatan', 'llama-server tidak terhubung');
    else chip('ok', 'Server aktif');

    // kartu AI Asisten
    const model = s.model_tampil || s.model || '';
    if (s.status === 'siap') {
      setStatus('stChat', 'ok', 'Sesi berjalan · ' + potong(model, 28) + (s.skill ? ' · ' + labelSkill(s.skill) : ''));
      $('aksiChat').textContent = 'Lanjutkan sesi';
    } else if (s.status === 'memuat') {
      setStatus('stChat', 'muat', 'Memuat model...');
      $('aksiChat').textContent = 'Buka AI Asisten';
    } else if (s.status === 'error') {
      setStatus('stChat', 'mati', 'Gagal memuat: ' + potong(s.pesan, 40));
      $('aksiChat').textContent = 'Buka AI Asisten';
    } else if (ag && ag.chat_id) {
      setStatus('stChat', 'kerja', 'Obrolan sedang dikerjakan Agent');
      $('aksiChat').textContent = 'Buka AI Asisten';
    } else {
      setStatus('stChat', 'diam', nChat ? nChat + ' obrolan tersimpan' : 'Belum ada obrolan');
      $('aksiChat').textContent = 'Buka AI Asisten';
    }

    // kartu Agent
    if (ag) {
      setStatus('stAgent', 'kerja', 'Bekerja · ' + potong(ag.tugas, 34));
      $('aksiAgent').textContent = 'Lihat proses';
    } else {
      const n = Array.isArray(runs) ? runs.length : null;
      const st = n && STATUS_RUN[runs[0].status];
      setStatus('stAgent', 'diam', n ? n + ' proses tersimpan' + (st ? ' · terakhir ' + st[0].toLowerCase() : '') : 'Belum ada proses');
      $('aksiAgent').textContent = 'Buka Agent';
    }

    // kondisi sistem
    const k = $('kondisi');
    k.textContent = '';
    if (utama) {
      if (utama.ok === false) k.append(baris('Server model', 'mati', 'Tidak terhubung'));
      else k.append(baris('Server model', 'ok', 'Terhubung' + (utama.jumlah ? ' · ' + utama.jumlah + ' model' : '')));
    }
    k.append(baris('Model termuat', s.status === 'siap' ? 'ok' : s.status === 'memuat' ? 'muat' : 'diam',
      s.status === 'siap' ? potong(model, 30) : s.status === 'memuat' ? 'Memuat...' : 'Tidak ada (RAM kosong)'));
    k.append(baris('Agent', ag ? 'kerja' : 'diam', ag ? 'Bekerja' : 'Siap'));
    k.append(baris('Mode AUTO', s.auto ? 'peringatan' : 'diam', s.auto ? 'Nyala' : 'Mati'));

    // proses Agent terbaru
    const ul = $('daftarRun');
    ul.textContent = '';
    const terbaru = Array.isArray(runs) ? runs.slice(0, 4) : [];
    $('kartuRun').hidden = !terbaru.length;
    for (const r of terbaru) {
      const li = el('li');
      const a = el('a');
      a.href = 'agent.html?run=' + encodeURIComponent(r.id);
      const rt = el('span', 'rt');
      rt.append(el('b', '', potong(r.judul || r.id, 60)), el('small', '', waktuRingkas(r.dibuat)));
      a.append(rt);
      const st = STATUS_RUN[r.status];
      if (st) a.append(el('span', 'lencana' + (st[1] ? ' ' + st[1] : ''), st[0]));
      li.append(a);
      ul.append(li);
    }
  }
  function gambarPutus() {
    chip('mati', 'Server tidak terjangkau');
    setStatus('stChat', 'mati', 'Tidak bisa menghubungi server');
    setStatus('stAgent', 'mati', 'Tidak bisa menghubungi server');
  }

  /* ---------- muat data ---------- */
  async function muat() {
    if (memuat || !TOKEN) return;
    memuat = true;
    try {
      const s = await api('/api/status');
      const [c, r] = await Promise.all([api('/api/chat').catch(() => null), api('/api/agent/riwayat').catch(() => null)]);
      if (layar !== 'dasbor') tampil('dasbor');
      gambar(s, c && c.chat, r && r.run);
    } catch (e) {
      if (e.message !== '401') {
        if (layar !== 'dasbor') tampil('dasbor');
        gambarPutus();
      }
    } finally {
      memuat = false;
    }
  }
  function mulaiPoll() {
    clearInterval(timer);
    timer = setInterval(() => { if (!document.hidden && layar === 'dasbor') muat(); }, 5000);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && layar === 'dasbor') muat(); });

  /* ---------- token ---------- */
  $('btnToken').onclick = () => {
    const v = $('tokenInput').value.trim();
    if (!v) return;
    TOKEN = v; localStorage.setItem('aa_token', v);
    $('tokenPesan').textContent = ''; $('tokenInput').value = '';
    muat();
  };
  $('tokenInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('btnToken').click(); });
  $('btnGantiToken').onclick = () => {
    if (!confirm('Hapus token dari browser ini dan masukkan yang baru?')) return;
    localStorage.removeItem('aa_token'); TOKEN = '';
    tampil('token'); $('tokenPesan').textContent = '';
    toast('Token dihapus.');
  };

  /* ---------- mulai ---------- */
  const qs = new URLSearchParams(location.search);
  if (qs.get('token')) {
    TOKEN = qs.get('token'); localStorage.setItem('aa_token', TOKEN);
    history.replaceState(null, '', location.pathname);
  }
  if (!TOKEN) tampil('token');
  else { tampil('dasbor'); chip('muat', 'Menghubungkan...'); muat(); }
  mulaiPoll();
})();
