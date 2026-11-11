package id.aiasisten.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.util.Base64;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.webkit.JavascriptInterface;
import android.webkit.JsPromptResult;
import android.webkit.JsResult;
import android.webkit.MimeTypeMap;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.HttpURLConnection;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.List;

/**
 * AI Asisten untuk Android.
 *
 * Layar Beranda (asli Android): isi alamat server, Tes koneksi, tombol Masuk (muncul kalau server
 * ai_asisten aktif), alamat terakhir, versi aplikasi, dan pembaruan dari GitHub Releases.
 * Layar Web: halaman web asisten.py di WebView, persis sama dengan di browser, ditambah unggah berkas,
 * unduhan ke Download/AI Asisten, dialog asli, dan tautan luar dibuka di browser.
 */
public class MainActivity extends Activity {

    private static final String PREF = "pengaturan";
    private static final String KUNCI_ALAMAT = "alamat";
    private static final String KUNCI_RIWAYAT = "riwayat_alamat";
    private static final int MAKS_RIWAYAT = 5;
    private static final int KODE_BERKAS = 7;
    private static final String NAMA_JEMBATAN = "AiAsistenAndroid";

    /** Disuntikkan setelah halaman selesai dimuat: klik <a download href="blob:..."> dialihkan ke aplikasi. */
    private static final String JS_UNDUH =
        "(function(){if(window.__aaUnduh)return;window.__aaUnduh=1;"
        + "var asli=HTMLAnchorElement.prototype.click;"
        + "HTMLAnchorElement.prototype.click=function(){"
        + "var h=this.href||'';"
        + "if(this.hasAttribute('download')&&(h.indexOf('blob:')===0||h.indexOf('data:')===0)){"
        + "var nama=this.getAttribute('download')||'unduhan';"
        + "fetch(h).then(function(r){return r.blob();}).then(function(b){"
        + "var fr=new FileReader();fr.onload=function(){var s=String(fr.result);"
        + NAMA_JEMBATAN + ".simpan(s.substring(s.indexOf(',')+1),nama,b.type||'');};"
        + "fr.readAsDataURL(b);}).catch(function(e){" + NAMA_JEMBATAN + ".pesan('Unduhan gagal: '+e);});"
        + "return;}"
        + "return asli.apply(this,arguments);};})();";

    // warna (sama dengan variabel di web/index.css)
    private boolean gelap;
    private int cLatar, cPanel, cPanel2, cGaris, cTeks, cRedup, cAksen, cOk, cBahaya, cIzin;

    // layar
    private FrameLayout akar;
    private ScrollView layarBeranda;
    private FrameLayout layarWeb;
    private WebView web;
    private ProgressBar bilahWeb;

    // beranda: server
    private EditText isianAlamat;
    private TextView titikStatus, teksStatus, tombolMasuk, tombolTes;
    private LinearLayout wadahRiwayat, barisRiwayat;
    private int nomorTes;               // hasil tes lama yang terlambat datang diabaikan
    private boolean serverAktif;
    private String alamatAktif = "";    // http://host:port yang lolos tes
    private String muatLengkap = "";    // alamat lengkap (boleh dengan ?token=) yang dimuat saat Masuk
    private String alamatWeb = "";      // server yang sedang dimuat di WebView

    // beranda: pembaruan
    private TextView teksPembaruan, tombolPasang, tombolCekLagi;
    private ProgressBar bilahUnduh;
    private Pembaruan.Rilis rilisBaru;
    private boolean sedangUnduh;

    private ValueCallback<Uri[]> panggilBerkas;

    /* ============================================================ siklus hidup */

    @Override
    protected void onCreate(Bundle simpanan) {
        super.onCreate(simpanan);
        aturWarna();
        aturBilahSistem();
        akar = new FrameLayout(this);
        akar.setBackgroundColor(cLatar);
        bangunWeb();
        bangunBeranda();
        setContentView(akar);
        //noinspection ResultOfMethodCallIgnored
        berkasPembaruan().delete();   // sisa unduhan pembaruan sebelumnya

        String tersimpan = pref().getString(KUNCI_ALAMAT, "");
        isianAlamat.setText(tersimpan);
        isianAlamat.setSelection(isianAlamat.getText().length());
        gambarRiwayat();
        tampilBeranda();
        if (!tersimpan.isEmpty()) tesKoneksi();
        else setStatus(cRedup, "Isi alamat server lalu tekan Tes koneksi.");
        cekPembaruan();
        tanganiIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        tanganiIntent(i);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (layarWeb.getVisibility() == View.VISIBLE) {
            if (web.canGoBack()) web.goBack();
            else tampilBeranda();
            return;
        }
        super.onBackPressed();
    }

    /* ============================================================ warna dan gaya */

    private void aturWarna() {
        gelap = Build.VERSION.SDK_INT < 29
            || (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
               == Configuration.UI_MODE_NIGHT_YES;
        if (gelap) {
            cLatar = 0xFF111317; cPanel = 0xFF1A1D23; cPanel2 = 0xFF20242C; cGaris = 0xFF2A2E37;
            cTeks = 0xFFE6E8EC; cRedup = 0xFF8B93A1; cAksen = 0xFF5B9CFF;
            cOk = 0xFF4CC38A; cBahaya = 0xFFFF6B6B; cIzin = 0xFFD9A441;
        } else {
            cLatar = 0xFFF4F5F7; cPanel = 0xFFFFFFFF; cPanel2 = 0xFFF3F5F9; cGaris = 0xFFDDE1E7;
            cTeks = 0xFF1B1F27; cRedup = 0xFF6B7280; cAksen = 0xFF2563EB;
            cOk = 0xFF16A34A; cBahaya = 0xFFDC2626; cIzin = 0xFFB7791F;
        }
    }

    @SuppressWarnings("deprecation")
    private void aturBilahSistem() {
        Window w = getWindow();
        w.setStatusBarColor(cLatar);
        w.setNavigationBarColor(cLatar);
        if (!gelap) {
            int f = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 26) f |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            w.getDecorView().setSystemUiVisibility(f);
        }
    }

    private int dp(float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v,
            getResources().getDisplayMetrics()));
    }

    private GradientDrawable kotak(int isi, float sudutDp, int garis) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(isi);
        g.setCornerRadius(dp(sudutDp));
        if (garis != 0) g.setStroke(dp(1), garis);
        return g;
    }

    private TextView teks(String isi, float sp, int warna, boolean tebal) {
        TextView t = new TextView(this);
        t.setText(isi);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(warna);
        if (tebal) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    /** Tombol datar dengan efek sentuh. utama = latar aksen, selain itu bergaris. */
    private TextView tombol(String isi, boolean utama) {
        TextView t = teks(isi, 15, utama ? 0xFFFFFFFF : cTeks, true);
        t.setGravity(Gravity.CENTER);
        t.setPadding(dp(16), dp(12), dp(16), dp(12));
        t.setMinHeight(dp(46));
        GradientDrawable dasar = utama ? kotak(cAksen, 12, 0) : kotak(cPanel2, 12, cGaris);
        t.setBackground(new RippleDrawable(ColorStateList.valueOf(0x33808080), dasar, null));
        t.setClickable(true);
        t.setFocusable(true);
        return t;
    }

    private LinearLayout kartu(String judul) {
        LinearLayout k = new LinearLayout(this);
        k.setOrientation(LinearLayout.VERTICAL);
        k.setBackground(kotak(cPanel, 18, cGaris));
        k.setPadding(dp(18), dp(16), dp(18), dp(18));
        TextView j = teks(judul, 13, cRedup, true);
        j.setLetterSpacing(0.08f);
        k.addView(j);
        return k;
    }

    private LinearLayout.LayoutParams lp(int atas) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(atas);
        return p;
    }

    /* ============================================================ layar Beranda */

    private void bangunBeranda() {
        layarBeranda = new ScrollView(this);
        layarBeranda.setFillViewport(true);
        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.VERTICAL);
        isi.setPadding(dp(20), dp(28), dp(20), dp(28));
        layarBeranda.addView(isi);

        // kepala
        ImageView ikon = new ImageView(this);
        ikon.setImageResource(R.mipmap.ic_launcher_fg);
        LinearLayout.LayoutParams lpIkon = new LinearLayout.LayoutParams(dp(112), dp(112));
        lpIkon.gravity = Gravity.CENTER_HORIZONTAL;
        isi.addView(ikon, lpIkon);
        TextView judul = teks("AI Asisten", 26, cTeks, true);
        judul.setGravity(Gravity.CENTER);
        isi.addView(judul, lp(0));
        TextView sub = teks("Asisten AI lokal di Raspberry Pi", 14, cRedup, false);
        sub.setGravity(Gravity.CENTER);
        isi.addView(sub, lp(4));

        // kartu server
        LinearLayout ks = kartu("SERVER");
        isi.addView(ks, lp(24));

        isianAlamat = new EditText(this);
        isianAlamat.setSingleLine(true);
        isianAlamat.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        isianAlamat.setImeOptions(EditorInfo.IME_ACTION_GO);
        isianAlamat.setHint("http://192.168.1.10:8090");
        isianAlamat.setTextColor(cTeks);
        isianAlamat.setHintTextColor(cRedup);
        isianAlamat.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        isianAlamat.setBackground(kotak(cPanel2, 12, cGaris));
        isianAlamat.setPadding(dp(14), dp(12), dp(14), dp(12));
        ks.addView(isianAlamat, lp(12));
        isianAlamat.setOnEditorActionListener((v, aksi, ev) -> {
            tesKoneksi();
            return true;
        });
        isianAlamat.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void afterTextChanged(Editable s) {
                if (!isianAlamat.hasFocus()) return;   // diisi program, bukan diketik
                nomorTes++;
                setAktif(false);
                setStatus(cRedup, "Belum dites.");
            }
        });

        LinearLayout baris = new LinearLayout(this);
        baris.setOrientation(LinearLayout.HORIZONTAL);
        baris.setGravity(Gravity.CENTER_VERTICAL);
        titikStatus = teks("●", 16, cRedup, false);
        teksStatus = teks("", 14, cRedup, false);
        teksStatus.setPadding(dp(8), 0, dp(8), 0);
        tombolTes = tombol("Tes koneksi", false);
        tombolTes.setOnClickListener(v -> tesKoneksi());
        baris.addView(titikStatus);
        baris.addView(teksStatus, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        baris.addView(tombolTes);
        ks.addView(baris, lp(12));

        tombolMasuk = tombol("Masuk  →", true);
        tombolMasuk.setTextSize(TypedValue.COMPLEX_UNIT_SP, 17);
        tombolMasuk.setOnClickListener(v -> masuk());
        tombolMasuk.setVisibility(View.GONE);
        ks.addView(tombolMasuk, lp(14));

        wadahRiwayat = new LinearLayout(this);
        wadahRiwayat.setOrientation(LinearLayout.VERTICAL);
        wadahRiwayat.addView(teks("Alamat terakhir", 13, cRedup, false));
        barisRiwayat = new LinearLayout(this);
        barisRiwayat.setOrientation(LinearLayout.VERTICAL);
        wadahRiwayat.addView(barisRiwayat);
        ks.addView(wadahRiwayat, lp(16));

        TextView petunjuk = teks("Alamat tampil di terminal saat asisten.py dijalankan. Boleh ditempel "
            + "lengkap dengan ?token=... supaya token langsung tersimpan. HP harus satu jaringan dengan Pi "
            + "(Wi-Fi yang sama atau Tailscale).", 12.5f, cRedup, false);
        ks.addView(petunjuk, lp(14));

        // kartu aplikasi
        LinearLayout ka = kartu("APLIKASI");
        isi.addView(ka, lp(16));
        ka.addView(teks("Versi " + versiNama() + "  ·  build " + versiKode(), 16, cTeks, true), lp(10));
        teksPembaruan = teks("", 14, cRedup, false);
        ka.addView(teksPembaruan, lp(6));
        bilahUnduh = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bilahUnduh.setMax(1000);
        bilahUnduh.setVisibility(View.GONE);
        ka.addView(bilahUnduh, lp(10));
        tombolPasang = tombol("Unduh dan pasang", true);
        tombolPasang.setVisibility(View.GONE);
        tombolPasang.setOnClickListener(v -> unduhDanPasang());
        ka.addView(tombolPasang, lp(12));

        LinearLayout barisApp = new LinearLayout(this);
        barisApp.setOrientation(LinearLayout.HORIZONTAL);
        tombolCekLagi = tombol("Periksa pembaruan", false);
        tombolCekLagi.setOnClickListener(v -> cekPembaruan());
        TextView rilis = tombol("Halaman rilis", false);
        rilis.setOnClickListener(v -> bukaLuar(Uri.parse(Versi.HALAMAN_RILIS)));
        LinearLayout.LayoutParams kiri = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        LinearLayout.LayoutParams kanan = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        kanan.leftMargin = dp(10);
        barisApp.addView(tombolCekLagi, kiri);
        barisApp.addView(rilis, kanan);
        ka.addView(barisApp, lp(12));

        akar.addView(layarBeranda, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    private void tampilBeranda() {
        layarWeb.setVisibility(View.GONE);
        layarBeranda.setVisibility(View.VISIBLE);
    }

    private void tampilWeb() {
        sembunyikanPapanKetik();
        layarBeranda.setVisibility(View.GONE);
        layarWeb.setVisibility(View.VISIBLE);
    }

    private void sembunyikanPapanKetik() {
        InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        if (imm != null) imm.hideSoftInputFromWindow(isianAlamat.getWindowToken(), 0);
        isianAlamat.clearFocus();
    }

    private void setStatus(int warna, String pesan) {
        titikStatus.setTextColor(warna);
        teksStatus.setText(pesan);
    }

    private void setAktif(boolean aktif) {
        serverAktif = aktif;
        tombolMasuk.setVisibility(aktif ? View.VISIBLE : View.GONE);
    }

    /* ------------------------------------------------------------ alamat dan tes koneksi */

    private SharedPreferences pref() {
        return getSharedPreferences(PREF, Context.MODE_PRIVATE);
    }

    private List<String> riwayat() {
        List<String> d = new ArrayList<>();
        for (String s : pref().getString(KUNCI_RIWAYAT, "").split("\n")) {
            if (!s.trim().isEmpty()) d.add(s.trim());
        }
        return d;
    }

    private void simpanAlamat(String dasar) {
        List<String> d = riwayat();
        d.remove(dasar);
        d.add(0, dasar);
        while (d.size() > MAKS_RIWAYAT) d.remove(d.size() - 1);
        StringBuilder sb = new StringBuilder();
        for (String s : d) sb.append(s).append('\n');
        pref().edit().putString(KUNCI_ALAMAT, dasar).putString(KUNCI_RIWAYAT, sb.toString()).apply();
        gambarRiwayat();
    }

    private void gambarRiwayat() {
        barisRiwayat.removeAllViews();
        List<String> d = riwayat();
        wadahRiwayat.setVisibility(d.isEmpty() ? View.GONE : View.VISIBLE);
        for (final String a : d) {
            LinearLayout b = new LinearLayout(this);
            b.setOrientation(LinearLayout.HORIZONTAL);
            b.setGravity(Gravity.CENTER_VERTICAL);
            b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x33808080),
                kotak(cPanel2, 10, 0), null));
            b.setPadding(dp(12), dp(4), dp(4), dp(4));
            TextView t = teks(a.replaceFirst("^https?://", ""), 14, cTeks, false);
            b.addView(t, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            TextView hapus = teks("✕", 15, cRedup, false);
            hapus.setPadding(dp(14), dp(8), dp(10), dp(8));
            hapus.setOnClickListener(v -> hapusRiwayat(a));
            b.addView(hapus);
            b.setOnClickListener(v -> {
                sembunyikanPapanKetik();
                isianAlamat.setText(a);
                tesKoneksi();
            });
            barisRiwayat.addView(b, lp(6));
        }
    }

    private void hapusRiwayat(String a) {
        List<String> d = riwayat();
        d.remove(a);
        StringBuilder sb = new StringBuilder();
        for (String s : d) sb.append(s).append('\n');
        pref().edit().putString(KUNCI_RIWAYAT, sb.toString()).apply();
        gambarRiwayat();
    }

    private void tesKoneksi() {
        sembunyikanPapanKetik();
        final String[] a = Versi.alamat(isianAlamat.getText().toString());
        setAktif(false);
        if (a == null) {
            setStatus(cBahaya, "Alamat tidak valid. Contoh: http://192.168.1.10:8090");
            return;
        }
        final int nomor = ++nomorTes;
        setStatus(cIzin, "Mengetes " + a[0].replaceFirst("^https?://", "") + " ...");
        tombolTes.setEnabled(false);
        new Thread(() -> {
            long mulai = System.currentTimeMillis();
            int warna;
            String pesan;
            boolean aktif = false;
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(a[0] + "/").openConnection();
                c.setConnectTimeout(4000);
                c.setReadTimeout(5000);
                c.setRequestProperty("User-Agent", "AiAsistenAndroid/" + versiNama());
                int kode = c.getResponseCode();
                String isi = "";
                if (kode == 200) {
                    try (InputStream in = c.getInputStream()) {
                        byte[] buf = new byte[65536];
                        int n, total = 0;
                        StringBuilder sb = new StringBuilder();
                        while (total < 65536 && (n = in.read(buf)) > 0) {
                            sb.append(new String(buf, 0, n, "UTF-8"));
                            total += n;
                        }
                        isi = sb.toString();
                    }
                }
                long ms = System.currentTimeMillis() - mulai;
                if (kode == 200 && Versi.halamanAiAsisten(isi)) {
                    aktif = true;
                    warna = cOk;
                    pesan = "Server AI Asisten aktif · " + ms + " ms";
                } else if (kode == 200) {
                    warna = cIzin;
                    pesan = "Terhubung, tapi ini bukan server AI Asisten (port dipakai aplikasi lain?)";
                } else {
                    warna = cIzin;
                    pesan = "Server menjawab kode " + kode + ", bukan halaman AI Asisten";
                }
            } catch (ConnectException e) {
                warna = cBahaya;
                pesan = "Tidak aktif: tidak ada yang menjawab di alamat ini (asisten.py belum jalan?)";
            } catch (SocketTimeoutException e) {
                warna = cBahaya;
                pesan = "Waktu habis: HP dan Pi mungkin beda jaringan";
            } catch (UnknownHostException e) {
                warna = cBahaya;
                pesan = "Nama alamat tidak dikenal";
            } catch (NoRouteToHostException e) {
                warna = cBahaya;
                pesan = "Tidak ada jalur ke alamat ini (beda jaringan?)";
            } catch (Exception e) {
                warna = cBahaya;
                pesan = "Gagal: " + e.getClass().getSimpleName()
                    + (e.getMessage() == null ? "" : " (" + e.getMessage() + ")");
            } finally {
                if (c != null) c.disconnect();
            }
            final int w = warna;
            final String p = pesan;
            final boolean ok = aktif;
            runOnUiThread(() -> {
                tombolTes.setEnabled(true);
                if (nomor != nomorTes) return;
                setStatus(w, p);
                setAktif(ok);
                if (ok) {
                    alamatAktif = a[0];
                    muatLengkap = a[1];
                    simpanAlamat(a[0]);
                }
            });
        }).start();
    }

    private void masuk() {
        if (!serverAktif || alamatAktif.isEmpty()) return;
        boolean sudahDimuat = alamatAktif.equals(alamatWeb) && web.getUrl() != null
            && web.getUrl().startsWith(alamatAktif) && !muatLengkap.contains("?");
        tampilWeb();
        if (!sudahDimuat) {
            alamatWeb = alamatAktif;
            web.clearHistory();
            web.loadUrl(muatLengkap);
        }
        muatLengkap = alamatAktif + "/";    // ?token= cukup sekali: halaman menyimpannya sendiri
    }

    /* ============================================================ pembaruan */

    private String versiNama() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
        }
    }

    @SuppressWarnings("deprecation")
    private long versiKode() {
        try {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    private File berkasPembaruan() {
        return new File(getCacheDir(), "pembaruan.apk");
    }

    private void cekPembaruan() {
        if (sedangUnduh) return;
        teksPembaruan.setTextColor(cRedup);
        teksPembaruan.setText("Memeriksa pembaruan...");
        tombolPasang.setVisibility(View.GONE);
        tombolCekLagi.setEnabled(false);
        new Thread(() -> {
            Pembaruan.Rilis r = null;
            String galat = null;
            try {
                r = Pembaruan.cekTerbaru();
            } catch (Exception e) {
                galat = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            }
            final Pembaruan.Rilis hasil = r;
            final String g = galat;
            runOnUiThread(() -> {
                tombolCekLagi.setEnabled(true);
                if (g != null) {
                    teksPembaruan.setTextColor(cIzin);
                    teksPembaruan.setText("Tidak bisa memeriksa pembaruan: " + g);
                } else if (hasil == null) {
                    teksPembaruan.setTextColor(cRedup);
                    teksPembaruan.setText("Belum ada rilis di GitHub.");
                } else if (hasil.build > versiKode()) {
                    rilisBaru = hasil;
                    teksPembaruan.setTextColor(cOk);
                    teksPembaruan.setText("Pembaruan tersedia: versi " + hasil.versi + " · build " + hasil.build
                        + (hasil.ukuran > 0 ? "  (" + Math.max(1, hasil.ukuran / 1024) + " KB)" : ""));
                    tombolPasang.setText("Unduh dan pasang versi " + hasil.versi);
                    tombolPasang.setVisibility(View.VISIBLE);
                } else {
                    teksPembaruan.setTextColor(cRedup);
                    teksPembaruan.setText("Sudah versi terbaru.");
                }
            });
        }).start();
    }

    private void unduhDanPasang() {
        if (rilisBaru == null || sedangUnduh) return;
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            new AlertDialog.Builder(this)
                .setTitle("Izin memasang aplikasi")
                .setMessage("Aktifkan \"Izinkan dari sumber ini\" untuk AI Asisten, lalu kembali dan tekan "
                    + "tombol pasang lagi.")
                .setPositiveButton("Buka pengaturan", (d, w) -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:" + getPackageName())));
                    } catch (ActivityNotFoundException e) {
                        bukaLuar(Uri.parse(Versi.HALAMAN_RILIS));
                    }
                })
                .setNegativeButton("Batal", null)
                .show();
            return;
        }
        final Pembaruan.Rilis r = rilisBaru;
        final File f = berkasPembaruan();
        sedangUnduh = true;
        tombolPasang.setEnabled(false);
        tombolCekLagi.setEnabled(false);
        bilahUnduh.setProgress(0);
        bilahUnduh.setVisibility(View.VISIBLE);
        teksPembaruan.setTextColor(cRedup);
        teksPembaruan.setText("Mengunduh " + r.nama + " ...");
        new Thread(() -> {
            String galat = null;
            try {
                Pembaruan.unduh(r, f, (dapat, total) -> runOnUiThread(() -> {
                    if (total > 0) bilahUnduh.setProgress((int) (dapat * 1000 / total));
                    teksPembaruan.setText("Mengunduh " + (dapat / 1024) + " KB"
                        + (total > 0 ? " dari " + (total / 1024) + " KB" : ""));
                }));
                runOnUiThread(() -> teksPembaruan.setText("Menyiapkan pemasangan..."));
                Pembaruan.pasang(MainActivity.this, f);
            } catch (Exception e) {
                galat = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            }
            final String g = galat;
            runOnUiThread(() -> {
                sedangUnduh = false;
                tombolPasang.setEnabled(true);
                tombolCekLagi.setEnabled(true);
                bilahUnduh.setVisibility(View.GONE);
                if (g != null) gagalPasang(g);
                else teksPembaruan.setText("Menunggu konfirmasi pemasangan dari Android...");
            });
        }).start();
    }

    private void gagalPasang(String alasan) {
        teksPembaruan.setTextColor(cBahaya);
        teksPembaruan.setText("Pembaruan gagal: " + alasan
            + ". Bisa juga diunduh manual dari Halaman rilis.");
    }

    /** Hasil PackageInstaller (lihat Pembaruan.pasang). */
    private void tanganiIntent(Intent i) {
        if (i == null || !Pembaruan.AKSI_PASANG.equals(i.getAction())) return;
        int status = i.getIntExtra(PackageInstaller.EXTRA_STATUS, Integer.MIN_VALUE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent konfirmasi = i.getParcelableExtra(Intent.EXTRA_INTENT);
            if (konfirmasi != null) {
                try {
                    startActivity(konfirmasi);
                    return;
                } catch (Exception e) {
                    gagalPasang("pemasang Android tidak bisa dibuka");
                    return;
                }
            }
            gagalPasang("Android tidak memberi layar konfirmasi");
        } else if (status == PackageInstaller.STATUS_SUCCESS) {
            teksPembaruan.setTextColor(cOk);
            teksPembaruan.setText("Pembaruan terpasang.");
            tombolPasang.setVisibility(View.GONE);
        } else if (status == PackageInstaller.STATUS_FAILURE_ABORTED) {
            teksPembaruan.setTextColor(cRedup);
            teksPembaruan.setText("Pemasangan dibatalkan. Tekan tombol pasang untuk mencoba lagi.");
        } else if (status != Integer.MIN_VALUE) {
            String pesan = i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            gagalPasang(pesan == null ? "kode " + status : pesan);
        }
    }

    /* ============================================================ layar Web */

    private void bangunWeb() {
        layarWeb = new FrameLayout(this);
        web = new WebView(this);
        web.setBackgroundColor(cLatar);
        layarWeb.addView(web, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        bilahWeb = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bilahWeb.setMax(100);
        bilahWeb.setVisibility(View.GONE);
        layarWeb.addView(bilahWeb, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(3), Gravity.TOP));
        akar.addView(layarWeb, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        aturWeb();
    }

    private boolean sesamaServer(Uri u) {
        if (alamatWeb.isEmpty()) return true;
        Uri a = Uri.parse(alamatWeb);
        return a.getHost() != null && a.getHost().equalsIgnoreCase(u.getHost())
            && a.getPort() == u.getPort();
    }

    private void aturWeb() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);           // localStorage: token, pilihan skill/model, cfg Agent
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setSupportZoom(false);
        s.setTextZoom(100);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setUserAgentString(s.getUserAgentString() + " AiAsistenAndroid/" + versiNama());

        web.addJavascriptInterface(new Jembatan(), NAMA_JEMBATAN);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                String skema = u.getScheme() == null ? "" : u.getScheme();
                if ((skema.equals("http") || skema.equals("https")) && sesamaServer(u)) return false;
                bukaLuar(u);
                return true;
            }

            @Override
            public void onPageStarted(WebView v, String url, android.graphics.Bitmap ikon) {
                bilahWeb.setProgress(5);
                bilahWeb.setVisibility(View.VISIBLE);
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                bilahWeb.setVisibility(View.GONE);
                v.evaluateJavascript(JS_UNDUH, null);
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (!r.isForMainFrame()) return;
                // Koneksi putus: kembali ke Beranda dengan pesan, tombol Masuk disembunyikan.
                alamatWeb = "";
                v.stopLoading();
                v.loadUrl("about:blank");
                tampilBeranda();
                setAktif(false);
                setStatus(cBahaya, "Koneksi ke server terputus: " + e.getDescription()
                    + ". Tekan Tes koneksi untuk mencoba lagi.");
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView v, int p) {
                bilahWeb.setProgress(Math.max(5, p));
            }

            @Override
            public boolean onJsAlert(WebView v, String url, String pesan, final JsResult r) {
                new AlertDialog.Builder(MainActivity.this).setMessage(pesan)
                    .setPositiveButton("OK", (d, w) -> r.confirm())
                    .setOnCancelListener(d -> r.confirm())
                    .show();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView v, String url, String pesan, final JsResult r) {
                new AlertDialog.Builder(MainActivity.this).setMessage(pesan)
                    .setPositiveButton("OK", (d, w) -> r.confirm())
                    .setNegativeButton("Batal", (d, w) -> r.cancel())
                    .setOnCancelListener(d -> r.cancel())
                    .show();
                return true;
            }

            @Override
            public boolean onJsPrompt(WebView v, String url, String pesan, String awal,
                                      final JsPromptResult r) {
                final EditText isian = new EditText(MainActivity.this);
                isian.setText(awal == null ? "" : awal);
                FrameLayout bungkus = new FrameLayout(MainActivity.this);
                bungkus.setPadding(dp(22), dp(4), dp(22), 0);
                bungkus.addView(isian);
                new AlertDialog.Builder(MainActivity.this).setMessage(pesan).setView(bungkus)
                    .setPositiveButton("OK", (d, w) -> r.confirm(isian.getText().toString()))
                    .setNegativeButton("Batal", (d, w) -> r.cancel())
                    .setOnCancelListener(d -> r.cancel())
                    .show();
                return true;
            }

            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb,
                                             FileChooserParams p) {
                if (panggilBerkas != null) panggilBerkas.onReceiveValue(null);
                panggilBerkas = cb;
                // Sengaja */*: atribut accept berisi ekstensi (.py, .zip, ...) sering membuat
                // pemilih berkas Android kosong. Halaman web tetap menyaring sendiri.
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                if (p.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE) {
                    i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                }
                try {
                    startActivityForResult(Intent.createChooser(i, "Pilih berkas"), KODE_BERKAS);
                } catch (ActivityNotFoundException e) {
                    panggilBerkas = null;
                    pesan("Tidak ada aplikasi pemilih berkas");
                    return false;
                }
                return true;
            }
        });

        web.setDownloadListener((url, ua, disposisi, mime, panjang) -> {
            if (url.startsWith("blob:") || url.startsWith("data:")) {
                String nama = URLUtil.guessFileName(url, disposisi, mime);
                web.evaluateJavascript("fetch('" + url.replace("'", "\\'") + "').then(r=>r.blob())"
                    + ".then(b=>{var f=new FileReader();f.onload=()=>{var s=String(f.result);"
                    + NAMA_JEMBATAN + ".simpan(s.substring(s.indexOf(',')+1),'"
                    + nama.replace("'", "") + "',b.type||'');};f.readAsDataURL(b);})", null);
            } else {
                bukaLuar(Uri.parse(url));
            }
        });
    }

    private void bukaLuar(Uri u) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, u));
        } catch (ActivityNotFoundException e) {
            pesan("Tidak ada aplikasi untuk membuka: " + u);
        }
    }

    private void pesan(final String t) {
        runOnUiThread(() -> Toast.makeText(MainActivity.this, t, Toast.LENGTH_LONG).show());
    }

    @Override
    protected void onActivityResult(int kode, int hasil, Intent data) {
        if (kode != KODE_BERKAS) {
            super.onActivityResult(kode, hasil, data);
            return;
        }
        if (panggilBerkas == null) return;
        Uri[] uri = null;
        if (hasil == RESULT_OK && data != null) {
            List<Uri> daftar = new ArrayList<>();
            if (data.getClipData() != null) {
                for (int i = 0; i < data.getClipData().getItemCount(); i++) {
                    daftar.add(data.getClipData().getItemAt(i).getUri());
                }
            } else if (data.getData() != null) {
                daftar.add(data.getData());
            }
            if (!daftar.isEmpty()) uri = daftar.toArray(new Uri[0]);
        }
        panggilBerkas.onReceiveValue(uri);
        panggilBerkas = null;
    }

    /* ------------------------------------------------------------ unduhan dari halaman */

    /** Dipanggil dari JavaScript halaman. */
    private class Jembatan {
        @JavascriptInterface
        public void simpan(final String base64, final String nama, final String mime) {
            new Thread(() -> {
                try {
                    pesan("Tersimpan: " + simpanBerkas(Base64.decode(base64, Base64.DEFAULT), nama, mime));
                } catch (Exception e) {
                    pesan("Gagal menyimpan " + nama + ": " + e.getMessage());
                }
            }).start();
        }

        @JavascriptInterface
        public void pesan(String t) {
            MainActivity.this.pesan(t);
        }
    }

    private String simpanBerkas(byte[] isi, String nama, String mime) throws Exception {
        String n = nama.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        if (n.isEmpty()) n = "unduhan";
        String m = mime;
        if (m == null || m.isEmpty()) {
            String ext = MimeTypeMap.getFileExtensionFromUrl(n.replace(' ', '_'));
            m = ext == null ? null : MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
            if (m == null) m = "application/octet-stream";
        }
        if (Build.VERSION.SDK_INT >= 29) {
            ContentResolver cr = getContentResolver();
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.MediaColumns.DISPLAY_NAME, n);
            cv.put(MediaStore.MediaColumns.MIME_TYPE, m);
            cv.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/AI Asisten");
            cv.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri u = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (u == null) throw new Exception("MediaStore menolak");
            try (OutputStream o = cr.openOutputStream(u)) {
                if (o == null) throw new Exception("tidak bisa menulis");
                o.write(isi);
            }
            cv.clear();
            cv.put(MediaStore.MediaColumns.IS_PENDING, 0);
            cr.update(u, cv, null, null);
            return "Download/AI Asisten/" + n;
        }
        File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (dir == null) dir = getFilesDir();
        if (!dir.exists() && !dir.mkdirs()) throw new Exception("folder tidak bisa dibuat");
        File f = new File(dir, n);
        try (FileOutputStream o = new FileOutputStream(f)) {
            o.write(isi);
        }
        return f.getAbsolutePath();
    }
}
