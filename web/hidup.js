/* hidup.js - pelengkap tampilan "hidup" untuk Sesi AI Asisten dan Sesi Agent.
   Tidak menyentuh logika aplikasi: hanya (1) menaruh layar sambutan berisi contoh di #pesan yang masih kosong,
   dan (2) menampilkan tombol "ke bawah" saat riwayat digulir menjauh dari pesan terbaru. */
(function () {
  'use strict';
  var body = document.body;
  var agent = body.classList.contains('agent');
  var chat = body.classList.contains('halaman-chat');
  var pesan = document.getElementById('pesan');
  var input = document.getElementById('input');
  if (!pesan || !input || (!agent && !chat)) return;

  var CONTOH = agent ? [
    ['🧮', 'Buat kalkulator sederhana dengan Python, lengkap dengan pengujiannya'],
    ['🗂️', 'Buat skrip yang merapikan berkas di sebuah folder menurut jenisnya'],
    ['🌐', 'Buat halaman web daftar tugas (to-do) dengan HTML dan JavaScript']
  ] : [
    ['💡', 'Jelaskan cara kerja DNS dengan bahasa sederhana'],
    ['✉️', 'Bantu saya menulis email izin tidak masuk kerja yang sopan'],
    ['🐍', 'Beri 5 ide proyek Python untuk pemula beserta langkah awalnya']
  ];

  function el(tag, kelas, teks) {
    var e = document.createElement(tag);
    if (kelas) e.className = kelas;
    if (teks != null) e.textContent = teks;
    return e;
  }

  function buatSambut() {
    var s = el('div', 'sambut'); s.id = 'sambut';
    if (!agent) {      /* di Agent kartu "Tim siap" sudah menyapa; cukup contoh tugas */
      var ik = el('div', 'sb-ik', '✦'); ik.setAttribute('aria-hidden', 'true');
      s.appendChild(ik);
      s.appendChild(el('h3', '', 'Halo, ada yang bisa dibantu?'));
      s.appendChild(el('p', '', 'Ketik pertanyaan atau perintah di bawah, atau ketuk salah satu contoh ini.'));
    } else {
      s.classList.add('kompak');
    }
    var daftar = el('div', 'sb-saran');
    daftar.appendChild(el('div', 'sb-label', agent ? 'Contoh tugas' : 'Contoh'));
    CONTOH.forEach(function (c) {
      var b = el('button', 'sb-chip'); b.type = 'button';
      b.appendChild(el('span', 'e', c[0]));
      b.appendChild(el('span', 't', c[1]));
      b.onclick = function () {
        input.value = c[1];
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.focus();
      };
      daftar.appendChild(b);
    });
    s.appendChild(daftar);
    return s;
  }

  var sambut = buatSambut();
  var sedang = false;
  /* Chat: tampil selama #pesan kosong. Agent: tampil sampai ada pesan pengguna (kartu "Tim siap" tetap di atasnya). */
  function perlu() {
    if (agent) return !pesan.querySelector('.p.user');
    for (var i = 0; i < pesan.children.length; i++) if (pesan.children[i] !== sambut) return false;
    return true;
  }
  function atur() {
    if (sedang) return;
    sedang = true;
    try {
      var perluSekarang = perlu();
      if (perluSekarang && sambut.parentNode !== pesan) pesan.appendChild(sambut);
      else if (!perluSekarang && sambut.parentNode === pesan) pesan.removeChild(sambut);
      else if (perluSekarang && pesan.lastElementChild !== sambut) pesan.appendChild(sambut);
    } finally { sedang = false; }
  }
  new MutationObserver(atur).observe(pesan, {childList: true});
  atur();

  /* ---------- tombol "ke bawah" ---------- */
  var tombol = el('button', 'ke-bawah'); tombol.type = 'button';
  tombol.setAttribute('aria-label', 'Gulir ke pesan terbaru');
  tombol.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14"/><path d="M6 13l6 6 6-6"/></svg><span>Terbaru</span>';
  var induk = agent ? document.getElementById('isiPesan') : document.getElementById('layar_chat');
  var bawah = document.getElementById('bawah');
  if (induk) induk.appendChild(tombol);

  function kurangGerak() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  function periksaGulir() {
    var jauh = pesan.scrollHeight - pesan.scrollTop - pesan.clientHeight;
    tombol.classList.toggle('tampil', jauh > 220);
    if (chat && bawah) tombol.style.bottom = (bawah.offsetHeight + 12) + 'px';
  }
  pesan.addEventListener('scroll', periksaGulir, {passive: true});
  new MutationObserver(periksaGulir).observe(pesan, {childList: true, subtree: true, characterData: true});
  window.addEventListener('resize', periksaGulir);
  input.addEventListener('input', periksaGulir);
  tombol.onclick = function () {
    pesan.scrollTo({top: pesan.scrollHeight, behavior: kurangGerak() ? 'auto' : 'smooth'});
  };
  periksaGulir();
})();
