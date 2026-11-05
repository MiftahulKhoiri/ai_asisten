/* robot.js - maskot "Robi": robot putih bermata cyan yang bisa bergerak.
   Pemakaian: <span class="robot" data-robot></span>            (robot utuh)
              <span class="robot" data-robot="kepala"></span>   (hanya kepala, untuk logo kecil)
   Keadaan: data-keadaan="berpikir" (mata berdenyut). Ketuk robot untuk membuatnya melambai.
   Matanya mengikuti jari/kursor. Semua gerak dimatikan oleh robot.css bila perangkat meminta pengurangan gerak. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var nomor = 0;

  function templat(kepalaSaja, id) {
    var g = function (n) { return id + n; };
    var lewat = kepalaSaja ? '22 8 156 102' : '0 0 200 222';
    var s = '<svg xmlns="' + NS + '" viewBox="' + lewat + '" role="img" aria-label="Robot Robi" focusable="false">' +
      '<defs>' +
      '<linearGradient id="' + g('p') + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d9deea"/></linearGradient>' +
      '<linearGradient id="' + g('s') + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b3b55"/><stop offset="1" stop-color="#0a1522"/></linearGradient>' +
      '<radialGradient id="' + g('c') + '" cx=".5" cy=".4" r=".6"><stop offset="0" stop-color="#4fe3ff" stop-opacity=".22"/><stop offset="1" stop-color="#4fe3ff" stop-opacity="0"/></radialGradient>' +
      '</defs>';
    if (!kepalaSaja) {
      s += '<ellipse class="r-bayang" cx="100" cy="212" rx="40" ry="6" fill="#000" opacity=".16"/>' +
        '<g class="r-badan">' +
        '<rect class="r-lengan kiri" x="34" y="116" width="26" height="64" rx="13" fill="url(#' + g('p') + ')" transform="rotate(10 47 120)"/>' +
        '<rect class="r-lengan kanan" x="140" y="116" width="26" height="64" rx="13" fill="url(#' + g('p') + ')" transform="rotate(-10 153 120)"/>' +
        '<path d="M56 130C56 120 72 114 100 114S144 120 144 130V162C144 190 124 202 100 202S56 190 56 162Z" fill="url(#' + g('p') + ')"/>' +
        '<path d="M58 160H86V168H114V160H142" fill="none" stroke="#c4cbdb" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' +
        '<ellipse cx="74" cy="140" rx="5" ry="16" fill="#fff" opacity=".75" transform="rotate(14 74 140)"/>' +
        '<rect x="84" y="102" width="32" height="18" rx="8" fill="#cfd5e2"/>';
    } else {
      s += '<g class="r-badan">';
    }
    s += '<rect x="26" y="52" width="16" height="28" rx="8" fill="#cfd5e2"/><rect x="158" y="52" width="16" height="28" rx="8" fill="#cfd5e2"/>' +
      '<rect x="80" y="12" width="40" height="16" rx="8" fill="#d6dbe7"/>' +
      '<rect x="34" y="20" width="132" height="88" rx="36" fill="url(#' + g('p') + ')"/>' +
      '<rect x="46" y="33" width="108" height="62" rx="26" fill="url(#' + g('s') + ')"/>' +
      '<rect x="46" y="33" width="108" height="62" rx="26" fill="url(#' + g('c') + ')"/>' +
      '<g class="r-lihat">' +
      '<path class="r-mata" d="M62 68A13 13 0 0 1 88 68Z" fill="#4fe3ff"/>' +
      '<path class="r-mata" d="M112 68A13 13 0 0 1 138 68Z" fill="#4fe3ff"/>' +
      '<path class="r-mulut" d="M92 77Q100 88 108 77Z" fill="#4fe3ff"/>' +
      '</g>' +
      '<ellipse cx="62" cy="31" rx="17" ry="5" fill="#fff" opacity=".85" transform="rotate(-14 62 31)"/>' +
      '</g></svg>';
    return s;
  }

  var daftar = [];

  function pasang(el) {
    if (!el || el.__robot) return el;
    el.__robot = true;
    el.innerHTML = templat(el.getAttribute('data-robot') === 'kepala', 'rb' + (++nomor) + '-');
    if (el.getAttribute('data-robot') !== 'kepala') {
      el.addEventListener('click', function () { lambai(el); });
    }
    daftar.push(el);
    return el;
  }

  function lambai(el) {
    var tangan = el.querySelector('.r-lengan.kanan');
    el.classList.remove('melambai'); void el.offsetWidth; el.classList.add('melambai');
    setTimeout(function () { el.classList.remove('melambai'); }, 1300);
    if (tangan) el.classList.add('melompat');
    setTimeout(function () { el.classList.remove('melompat'); }, 700);
  }

  function keadaan(el, nama) {
    if (!el) return;
    if (nama) el.setAttribute('data-keadaan', nama); else el.removeAttribute('data-keadaan');
  }

  /* mata mengikuti pointer (maks. 5 satuan); dibatasi lewat requestAnimationFrame */
  var tunggu = false, px = 0, py = 0;
  function ikuti() {
    tunggu = false;
    for (var i = daftar.length - 1; i >= 0; i--) {
      var el = daftar[i];
      if (!el.isConnected) { daftar.splice(i, 1); continue; }
      var r = el.getBoundingClientRect();
      if (!r.width || r.bottom < 0 || r.top > innerHeight) continue;
      var dx = (px - (r.left + r.width / 2)) / Math.max(120, innerWidth / 2);
      var dy = (py - (r.top + r.height * .3)) / Math.max(120, innerHeight / 2);
      el.style.setProperty('--lx', (Math.max(-1, Math.min(1, dx)) * 5).toFixed(2));
      el.style.setProperty('--ly', (Math.max(-1, Math.min(1, dy)) * 3).toFixed(2));
    }
  }
  function gerak(e) {
    px = e.clientX; py = e.clientY;
    if (!tunggu) { tunggu = true; requestAnimationFrame(ikuti); }
  }
  window.addEventListener('pointermove', gerak, {passive: true});
  window.addEventListener('pointerdown', gerak, {passive: true});

  function pasangSemua(akar) {
    var semua = (akar || document).querySelectorAll('[data-robot]');
    for (var i = 0; i < semua.length; i++) pasang(semua[i]);
  }

  window.Robot = {pasang: pasang, pasangSemua: pasangSemua, keadaan: keadaan, lambai: lambai};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { pasangSemua(); });
  else pasangSemua();
})();
