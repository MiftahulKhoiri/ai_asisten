(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  let TOKEN = localStorage.getItem('aa_token') || '';
  let layar = '', chatId = null, sibuk = false, pollTimer = null, pollMs = 0;
  let kartu = {}, daftar = [];

  /* ---------- util ---------- */
  function esc(s) {
    return s.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  }
  function md(s) {
    return s.split('```').map((p, i) => {
      if (i % 2 === 1) {
        const nl = p.indexOf('\n');
        const kode = (nl >= 0 && /^[\w+-]*$/.test(p.slice(0, nl).trim())) ? p.slice(nl + 1) : p;
        return '<pre><code>' + esc(kode.replace(/\n$/, '')) + '</code></pre>';
      }
      return esc(p)
        .replace(/`([^`\n]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    }).join('');
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
  /* ---------- indikator "Berpikir" ---------- */
  const KATA_PIKIR = ['Berpikir', 'Menimbang jawaban', 'Menyusun jawaban', 'Masih berpikir'];
  let indEl = null, indTimer = null, indMulai = 0;
  function mulaiBerpikir() {
    hentiBerpikir();
    const p = document.createElement('div'); p.className = 'p berpikir';
    p.setAttribute('role', 'status'); p.setAttribute('aria-live', 'polite');
    p.innerHTML = '<div class="gel"><span class="orb"></span>' +
      '<span class="tulis"><span class="kata">Berpikir</span>' +
      '<span class="titik"><i></i><i></i><i></i></span></span>' +
      '<small class="detik"></small></div>';
    $('pesan').appendChild(p); indEl = p; indMulai = Date.now();
    const kata = p.querySelector('.kata'), detik = p.querySelector('.detik');
    indTimer = setInterval(() => {
      const d = Math.floor((Date.now() - indMulai) / 1000);
      kata.textContent = KATA_PIKIR[Math.min(Math.floor(d / 6), KATA_PIKIR.length - 1)];
      detik.textContent = d >= 3 ? d + ' dtk' : '';
    }, 1000);
    gulir(true);
  }
  function pastikanBerpikir() {
    if (!indEl) mulaiBerpikir();
  }
  function taruhDiBawah() {
    const b = $('pesan');
    if (indEl && b.lastElementChild !== indEl) { b.appendChild(indEl); gulir(); }
  }
  function hentiBerpikir() {
    clearInterval(indTimer); indTimer = null;
    if (indEl) { indEl.remove(); indEl = null; }
  }
  function tampil(nama) {
    layar = nama;
    for (const n of ['token', 'model', 'chat']) $('layar_' + n).hidden = (n !== nama);
    $('btnSelesai').hidden = (nama !== 'chat');
    $('btnMenu').hidden = (nama !== 'chat');
    if (nama !== 'chat') { $('judulChat').textContent = 'AI Asisten'; $('subModel').textContent = ''; }
  }
  function setPoll(ms) {
    if (ms === pollMs) return;
    pollMs = ms; clearInterval(pollTimer); pollTimer = setInterval(cekStatus, ms);
  }
  function ringkasTool(nama, a) {
    if (nama === 'jalankan_perintah') return '$ ' + (a.perintah || '');
    if (nama === 'tulis_file') return 'tulis ' + (a.path || '') + ' (' + String(a.isi || '').length + ' karakter)';
    return (nama + ' ' + (a.path || '')).trim();
  }

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

  /* ---------- pilihan skill ---------- */
  const NAMA_SKILL = {tanpa: 'tanpa skill', dasar: 'skill dasar', semua: 'semua skill'};
  let skill = null, jmlSkill = {tanpa: 0, dasar: 4, semua: 20};
  try { skill = localStorage.getItem('skill'); } catch (e) { /* abaikan */ }
  if (!NAMA_SKILL[skill]) skill = null;
  function ketSkill() {
    if (skill === 'tanpa') return 'Murni chat. Model tidak diberi tool, cocok untuk menguji kualitas jawaban.';
    if (skill === 'dasar') return jmlSkill.dasar + ' tool inti: jalankan perintah, baca file, tulis file, lihat folder. Hemat konteks.';
    return 'Semua ' + jmlSkill.semua + ' tool (cari, edit, git, info sistem, dll). Butuh model yang pintar memilih tool.';
  }
  function setSkill(v, simpan) {
    skill = v;
    if (simpan) { try { localStorage.setItem('skill', v); } catch (e) { /* abaikan */ } }
    for (const b of document.querySelectorAll('#seg button')) b.classList.toggle('on', b.dataset.skill === v);
    $('skillKet').textContent = ketSkill();
  }
  for (const b of document.querySelectorAll('#seg button')) b.onclick = () => setSkill(b.dataset.skill, true);

  /* ---------- status & model ---------- */
  async function cekStatus() {
    try {
      const s = await apij('/api/status');
      $('swAuto').checked = !!s.auto;
      if (s.status === 'siap') {
        $('subModel').textContent = s.model + (s.skill ? ' · ' + NAMA_SKILL[s.skill] : '');
        $('input').placeholder = s.skill === 'tanpa' ? 'Ketik pesan...' : 'Ketik perintah...';
        $('swAuto').closest('label').hidden = (s.skill === 'tanpa');
        if (layar !== 'chat') await masukChat();
        setPoll(15000);
      } else {
        if (layar === 'chat') toast('Sesi berakhir, model dibongkar.');
        if (layar !== 'model') tampil('model');
        renderModel(s);
        setPoll(s.status === 'memuat' ? 1500 : 5000);
      }
    } catch (e) {
      if (e.message !== '401' && layar === 'model') {
        $('modelPesan').className = 'err'; $('modelPesan').textContent = 'Tidak bisa terhubung ke server.';
      }
    }
  }
  function renderModel(s) {
    const box = $('daftarModel'), pesan = $('modelPesan');
    pesan.className = s.status === 'error' ? 'err' : '';
    pesan.textContent = s.status === 'memuat' ? (s.pesan || 'Memuat model...') :
                        s.status === 'error' ? ('Gagal: ' + s.pesan) : (s.pesan || '');
    box.className = s.status === 'memuat' ? 'mati' : '';
    $('seg').className = s.status === 'memuat' ? 'seg mati' : 'seg';
    if (s.skills) {
      jmlSkill = s.skills;
      $('nDasar').textContent = s.skills.dasar + ' skill';
      $('nSemua').textContent = s.skills.semua + ' skill';
    }
    if (!skill) skill = s.skill_bawaan || 'semua';
    setSkill(skill, false);
    box.innerHTML = '';
    for (const m of (s.models || [])) {
      const b = document.createElement('button'); b.className = 'model';
      const gb = m.mb ? (m.mb / 1024).toFixed(1) + ' GB' : '?';
      const hint = !m.mb ? '' : m.mb <= 1500 ? 'ringan, cepat' : m.mb <= 3000 ? 'sedang' : 'berat, lebih lambat';
      b.innerHTML = '<span class="nama">' + esc(m.id) + '</span><span class="meta">' + gb +
        (hint ? ' · ' + hint : '') + (m.llama === 'loaded' ? ' · sudah termuat' : '') + '</span>';
      b.onclick = () => pilihModel(m.id);
      box.appendChild(b);
    }
  }
  async function pilihModel(id) {
    try { await apij('/api/model/pilih', {method: 'POST', body: {model: id, skill}}); }
    catch (e) { if (e.message !== '401') { $('modelPesan').className = 'err'; $('modelPesan').textContent = e.message; } return; }
    $('modelPesan').className = ''; $('modelPesan').textContent = 'Memuat ' + id + ' ...';
    $('daftarModel').className = 'mati'; $('seg').className = 'seg mati';
    setPoll(1500); cekStatus();
  }
  async function selesai() {
    if (!confirm('Akhiri sesi dan bongkar model dari memori?')) return;
    try { await apij('/api/model/selesai', {method: 'POST', body: {}}); } catch (e) { toast(e.message); return; }
    chatId = null; tampil('model'); cekStatus();
  }

  /* ---------- daftar chat ---------- */
  async function muatDaftarChat() {
    try { daftar = (await apij('/api/chat')).chat; } catch (e) { return; }
    const box = $('daftarChat'); box.innerHTML = '';
    for (const c of daftar) {
      const d = document.createElement('div'); d.className = 'chat' + (c.id === chatId ? ' aktif' : '');
      const t = document.createElement('button'); t.className = 't';
      t.innerHTML = '<b>' + esc(c.judul) + '</b><small>' + esc((c.diubah || '').replace('T', ' ')) + '</small>';
      t.onclick = () => bukaChat(c.id);
      const x = document.createElement('button'); x.className = 'x'; x.textContent = '✕'; x.setAttribute('aria-label', 'Hapus');
      x.onclick = async () => {
        if (!confirm('Hapus obrolan ini?')) return;
        try { await apij('/api/chat/' + c.id, {method: 'DELETE'}); } catch (e) { toast(e.message); return; }
        if (c.id === chatId) { chatId = null; localStorage.removeItem('aa_chat'); await chatBaru(); } else muatDaftarChat();
      };
      d.append(t, x); box.appendChild(d);
    }
  }
  async function masukChat() {
    tampil('chat');
    await muatDaftarChat();
    const terakhir = localStorage.getItem('aa_chat');
    if (terakhir && daftar.some(c => c.id === terakhir)) await bukaChat(terakhir); else await chatBaru();
  }
  async function chatBaru() {
    try {
      const c = await apij('/api/chat/baru', {method: 'POST', body: {}});
      chatId = c.id; localStorage.setItem('aa_chat', chatId);
      renderPesan([]); $('judulChat').textContent = 'Obrolan baru';
      tutupDrawer(); muatDaftarChat();
    } catch (e) { if (e.message !== '401') toast(e.message); }
  }
  async function bukaChat(id) {
    try {
      const c = await apij('/api/chat/' + id);
      chatId = c.id; localStorage.setItem('aa_chat', chatId);
      $('judulChat').textContent = c.judul || 'Obrolan';
      renderPesan(c.pesan || []); tutupDrawer(); muatDaftarChat();
    } catch (e) { if (e.message !== '401') { toast(e.message); await chatBaru(); } }
  }
  function tutupDrawer() { $('drawer').classList.remove('buka'); $('tirai').hidden = true; }

  /* ---------- render pesan ---------- */
  function tambahUser(teks) {
    const p = document.createElement('div'); p.className = 'p user';
    const g = document.createElement('div'); g.className = 'gel'; g.textContent = teks;
    p.appendChild(g); $('pesan').appendChild(p); gulir(true);
  }
  function tambahAsisten(teks) {
    const p = document.createElement('div'); p.className = 'p';
    const g = document.createElement('div'); g.className = 'gel'; g.innerHTML = md(teks);
    p.appendChild(g); $('pesan').appendChild(p); gulir();
    return g;
  }
  function tambahInfo(teks, err) {
    const d = document.createElement('div'); d.className = 'info' + (err ? ' err' : ''); d.textContent = teks;
    $('pesan').appendChild(d); gulir();
  }
  function kartuTool(id, ring, hasil) {
    const d = document.createElement('details'); d.className = 'tool';
    const s = document.createElement('summary'); s.textContent = '⚙ ' + ring + (hasil === undefined ? ' …' : '');
    const pre = document.createElement('pre'); pre.textContent = hasil === undefined ? '(menunggu hasil)' : hasil;
    d.append(s, pre); $('pesan').appendChild(d);
    kartu[id] = {s, pre, ring}; gulir();
  }
  function isiHasil(id, teks) {
    const k = kartu[id]; if (!k) return;
    k.s.textContent = '⚙ ' + k.ring; k.pre.textContent = teks;
  }
  function kartuKonfirmasi(ev) {
    const d = document.createElement('div'); d.className = 'konf';
    const t = document.createElement('b');
    t.textContent = ({tulis: 'Izinkan menulis file?', ubah: 'Izinkan mengubah file/folder?', hapus: 'Izinkan MENGHAPUS (ke tempat sampah)?', git: 'Izinkan perintah git?', jaringan: 'Izinkan akses jaringan?', proses: 'Izinkan menghentikan proses?'})[ev.jenis] || 'Izinkan menjalankan perintah?';
    const pre = document.createElement('pre'); pre.textContent = ev.ringkas + (ev.detail ? '\n\n' + ev.detail : '');
    const row = document.createElement('div'); row.className = 'baris';
    const ya = document.createElement('button'); ya.className = 'btn'; ya.textContent = 'Ya, izinkan';
    const tidak = document.createElement('button'); tidak.className = 'btn abu'; tidak.textContent = 'Tolak';
    const jawab = async setuju => {
      ya.disabled = true; tidak.disabled = true;
      try { await apij('/api/konfirmasi', {method: 'POST', body: {kid: ev.kid, setuju}}); row.textContent = setuju ? '✔ Diizinkan' : '✖ Ditolak'; }
      catch (e) { row.textContent = 'Gagal: ' + e.message; }
    };
    ya.onclick = () => jawab(true); tidak.onclick = () => jawab(false);
    row.append(ya, tidak); d.append(t, pre, row); $('pesan').appendChild(d); gulir(true);
  }
  function renderPesan(list) {
    hentiBerpikir(); $('pesan').innerHTML = ''; kartu = {};
    const hasil = {};
    for (const m of list) if (m.role === 'tool') hasil[m.tool_call_id] = m.content;
    for (const m of list) {
      if (m.role === 'user') tambahUser(m.content);
      else if (m.role === 'assistant') {
        if (m.content && m.content.trim()) tambahAsisten(m.content);
        for (const c of (m.tool_calls || [])) {
          let a = {}; try { a = JSON.parse(c.function.arguments || '{}'); } catch (e) { /* abaikan */ }
          kartuTool(c.id, ringkasTool(c.function.name, a), hasil[c.id]);
        }
      }
    }
    gulir(true);
  }

  /* ---------- kirim & stream ---------- */
  function setSibuk(v) {
    sibuk = v;
    $('btnKirim').textContent = v ? 'Stop' : 'Kirim';
    $('btnKirim').className = v ? 'btn merah' : 'btn';
  }
  function ukuranInput() {
    const i = $('input'); i.style.height = 'auto'; i.style.height = Math.min(i.scrollHeight, 160) + 'px';
  }
  async function kirim() {
    const teks = $('input').value.trim();
    if (!teks || sibuk || !chatId) return;
    $('input').value = ''; ukuranInput();
    tambahUser(teks); setSibuk(true); mulaiBerpikir();
    const st = {bubble: null, raw: '', pikir: null, pikirRaw: ''};
    try {
      const r = await api('/api/kirim', {method: 'POST', body: {id: chatId, teks}});
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
    } catch (e) { if (e.message !== '401') tambahInfo('⚠ ' + e.message, true); }
    finally { hentiBerpikir(); setSibuk(false); muatDaftarChat(); bukaJudul(); }
  }
  async function bukaJudul() {
    try { const c = await apij('/api/chat/' + chatId); $('judulChat').textContent = c.judul || 'Obrolan'; } catch (e) { /* abaikan */ }
  }
  function ribu(n) { return n >= 1000 ? (n / 1000).toFixed(1).replace('.0', '') + 'k' : String(n); }
  function teksInfo(ev) {
    let t = ev.tok + ' token · ' + ev.tok_s + ' tok/s';
    if (ev.pakai && ev.maks) {
      const pct = Math.min(100, Math.round(ev.pakai / ev.maks * 100));
      t += ' · konteks ' + ribu(ev.pakai) + '/' + ribu(ev.maks) + ' (' + pct + '%)' + (pct >= 85 ? ' ⚠ hampir penuh' : '');
    }
    return t;
  }
  function tangani(ev, st) {
    switch (ev.t) {
      case 'token':
        hentiBerpikir();  // animasi berhenti tepat saat jawaban mulai muncul
        if (!st.bubble) { st.bubble = tambahAsisten(''); st.raw = ''; }
        st.raw += ev.d; st.bubble.innerHTML = md(st.raw); gulir(); break;
      case 'pikir':     // model sedang bernalar: animasi tetap jalan
        if (!st.pikir) {
          const d = document.createElement('details'); d.className = 'pikir';
          const s = document.createElement('summary'); s.textContent = 'Berpikir…';
          const pre = document.createElement('pre'); d.append(s, pre); $('pesan').appendChild(d); st.pikir = pre;
        }
        st.pikirRaw += ev.d; st.pikir.textContent = st.pikirRaw; break;
      case 'tool':      // tool sedang jalan: tunggu hasilnya
        st.bubble = null; st.pikir = null; st.pikirRaw = '';
        kartuTool(ev.id, ev.ringkas); pastikanBerpikir(); break;
      case 'konfirmasi': // menunggu keputusan pengguna, bukan menunggu model
        hentiBerpikir(); kartuKonfirmasi(ev); break;
      case 'hasil':     // hasil tool masuk, model lanjut menyusun jawaban
        isiHasil(ev.id, ev.d); pastikanBerpikir(); break;
      case 'ringkas': tambahInfo('🗜 ' + ev.d); st.bubble = null; pastikanBerpikir(); break;
      case 'info': tambahInfo(teksInfo(ev), false); st.bubble = null; break;
      case 'error': hentiBerpikir(); tambahInfo('⚠ ' + ev.d, true); break;
      case 'batal': hentiBerpikir(); tambahInfo('Dibatalkan.'); break;
      case 'batas': hentiBerpikir(); tambahInfo('Batas langkah tercapai. Kirim pesan lanjutan jika perlu.'); break;
      default: break;
    }
    taruhDiBawah();     // indikator selalu di bawah elemen yang baru muncul
  }

  /* ---------- event ---------- */
  $('bawah').addEventListener('submit', e => {
    e.preventDefault();
    if (sibuk) { api('/api/stop', {method: 'POST', body: {}}).catch(() => {}); } else kirim();
  });
  $('input').addEventListener('input', ukuranInput);
  $('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!sibuk) kirim(); }
  });
  $('btnMenu').onclick = () => { $('drawer').classList.add('buka'); $('tirai').hidden = false; muatDaftarChat(); };
  $('tirai').onclick = tutupDrawer;
  $('btnBaru').onclick = () => { if (sibuk) { toast('Tunggu proses selesai atau tekan Stop.'); return; } chatBaru(); };
  $('btnSelesai').onclick = selesai;
  $('swAuto').onchange = async e => {
    const aktif = e.target.checked;
    if (aktif && !confirm('Mode AUTO menjalankan perintah dan menulis file TANPA konfirmasi (sudo, instal paket, hapus, git push, dan menghentikan proses tetap minta izin; perintah berbahaya tetap diblokir). Aktifkan?')) { e.target.checked = false; return; }
    try { await apij('/api/auto', {method: 'POST', body: {aktif}}); toast(aktif ? 'Mode AUTO aktif' : 'Mode AUTO mati'); }
    catch (err) { e.target.checked = !aktif; toast(err.message); }
  };
  $('btnToken').onclick = () => {
    const v = $('tokenInput').value.trim(); if (!v) return;
    TOKEN = v; localStorage.setItem('aa_token', v); $('tokenPesan').textContent = ''; cekStatus();
  };
  $('tokenInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('btnToken').click(); });

  /* ---------- mulai ---------- */
  const qs = new URLSearchParams(location.search);
  if (qs.get('token')) {
    TOKEN = qs.get('token'); localStorage.setItem('aa_token', TOKEN);
    history.replaceState(null, '', location.pathname);
  }
  if (!TOKEN) tampil('token');
  else { tampil('model'); $('modelPesan').textContent = 'Menghubungkan...'; setPoll(5000); cekStatus(); }
})();
