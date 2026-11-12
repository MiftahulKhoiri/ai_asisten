package id.aiasisten.app;

import android.annotation.SuppressLint;
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
import android.content.res.Configuration;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.JsPromptResult;
import android.webkit.JsResult;
import android.webkit.MimeTypeMap;
import android.webkit.URLUtil;
import android.webkit.WebBackForwardList;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

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
import java.util.concurrent.atomic.AtomicInteger;

/**
 * AI Asisten untuk Android.
 *
 * Beranda: halaman HTML lokal (assets/beranda.html) yang memakai CSS dan maskot Robi yang sama
 * persis dengan dasbor web (disalin dari web/ saat build). Isinya: alamat server, Tes koneksi,
 * tombol Masuk (hanya saat server aktif), alamat terakhir, versi aplikasi, dan pembaruan dari
 * GitHub Releases. Pekerjaan jaringannya dilakukan di sini lewat jembatan AiAsistenApp.
 *
 * Web: halaman asisten.py di WebView terpisah, persis seperti di browser, ditambah unggah berkas,
 * unduhan ke Download/AI Asisten, dialog asli, dan tautan luar dibuka di browser.
 */
public class MainActivity extends Activity {

    private static final String PREF = "pengaturan";
    private static final String KUNCI_ALAMAT = "alamat";
    private static final String KUNCI_RIWAYAT = "riwayat_alamat";
    private static final int MAKS_RIWAYAT = 5;
    private static final int KODE_BERKAS = 7;
    private static final String HALAMAN_BERANDA = "file:///android_asset/beranda.html";
    private static final String JEMBATAN_WEB = "AiAsistenAndroid";
    private static final String JEMBATAN_BERANDA = "AiAsistenApp";

    /** Disuntikkan setelah halaman server dimuat: klik <a download href="blob:..."> dialihkan ke aplikasi. */
    private static final String JS_UNDUH =
        "(function(){if(window.__aaUnduh)return;window.__aaUnduh=1;"
        + "var asli=HTMLAnchorElement.prototype.click;"
        + "HTMLAnchorElement.prototype.click=function(){"
        + "var h=this.href||'';"
        + "if(this.hasAttribute('download')&&(h.indexOf('blob:')===0||h.indexOf('data:')===0)){"
        + "var nama=this.getAttribute('download')||'unduhan';"
        + "fetch(h).then(function(r){return r.blob();}).then(function(b){"
        + "var fr=new FileReader();fr.onload=function(){var s=String(fr.result);"
        + JEMBATAN_WEB + ".simpan(s.substring(s.indexOf(',')+1),nama,b.type||'');};"
        + "fr.readAsDataURL(b);}).catch(function(e){" + JEMBATAN_WEB + ".pesan('Unduhan gagal: '+e);});"
        + "return;}"
        + "return asli.apply(this,arguments);};})();";

    private boolean gelap;
    private int cLatar;

    private WebView beranda;          // halaman lokal
    private FrameLayout layarWeb;
    private WebView web;              // halaman server asisten.py
    private ProgressBar bilahWeb;

    private final AtomicInteger nomorTes = new AtomicInteger();  // hasil tes lama diabaikan
    private volatile String alamatAktif = "";   // http://host:port yang lolos tes
    private volatile String muatLengkap = "";   // alamat lengkap (boleh ?token=) untuk Masuk berikutnya
    private String alamatWeb = "";              // server yang sedang dimuat di WebView
    private boolean bersihkanRiwayat;           // riwayat WebView dibuang setelah halaman baru selesai dimuat

    private volatile Pembaruan.Rilis rilisBaru;
    private volatile boolean sedangUnduh;

    private ValueCallback<Uri[]> panggilBerkas;

    /* ============================================================ siklus hidup */

    @Override
    protected void onCreate(Bundle simpanan) {
        super.onCreate(simpanan);
        gelap = Build.VERSION.SDK_INT < 29
            || (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
               == Configuration.UI_MODE_NIGHT_YES;
        cLatar = gelap ? 0xFF111317 : 0xFFF4F5F7;
        aturBilahSistem();

        FrameLayout akar = new FrameLayout(this);
        akar.setBackgroundColor(cLatar);
        bangunWeb(akar);
        bangunBeranda(akar);
        setContentView(akar);

        //noinspection ResultOfMethodCallIgnored
        berkasPembaruan().delete();   // sisa unduhan pembaruan sebelumnya
        tampilBeranda();
        beranda.loadUrl(HALAMAN_BERANDA);
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
        beranda.onResume();
    }

    @Override
    protected void onPause() {
        web.onPause();
        beranda.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        beranda.destroy();
        super.onDestroy();
    }

    /**
     * Kembali: di halaman server mundur hanya ke halaman server yang sah (bukan halaman kosong/galat
     * dari koneksi lama). Di halaman pertama muncul pilihan Beranda / Keluar; di Beranda minta
     * konfirmasi keluar.
     */
    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (layarWeb.getVisibility() == View.VISIBLE) {
            if (bisaMundurDiWeb()) web.goBack();
            else tanyaKeluar(true);
            return;
        }
        tanyaKeluar(false);
    }

    private boolean bisaMundurDiWeb() {
        if (alamatWeb.isEmpty()) return false;
        WebBackForwardList h = web.copyBackForwardList();
        int i = h.getCurrentIndex();
        if (i <= 0) return false;
        String sebelum = h.getItemAtIndex(i - 1).getUrl();
        return sebelum != null && sebelum.startsWith(alamatWeb + "/");
    }

    private void tanyaKeluar(boolean dariWeb) {
        AlertDialog.Builder b = new AlertDialog.Builder(this)
            .setTitle("AI Asisten")
            .setMessage(dariWeb ? "Kembali ke Beranda atau keluar dari aplikasi?" : "Keluar dari aplikasi?")
            .setPositiveButton("Keluar", (d, w) -> keluar())
            .setNegativeButton("Batal", null);
        if (dariWeb) b.setNeutralButton("Beranda", (d, w) -> tampilBeranda());
        b.show();
    }

    /** Tutup aplikasi (sesi di server tidak diakhiri: bisa dilanjutkan dari browser atau aplikasi). */
    private void keluar() {
        finishAndRemoveTask();
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

    private void tampilBeranda() {
        layarWeb.setVisibility(View.GONE);
        beranda.setVisibility(View.VISIBLE);
    }

    private void tampilWeb() {
        beranda.setVisibility(View.GONE);
        layarWeb.setVisibility(View.VISIBLE);
        web.requestFocus();
    }

    /* ============================================================ Beranda */

    @SuppressLint("SetJavaScriptEnabled")
    private void bangunBeranda(FrameLayout akar) {
        beranda = new WebView(this);
        beranda.setBackgroundColor(cLatar);
        WebSettings s = beranda.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);      // aset (file:///android_asset) tetap bisa dibaca
        s.setAllowContentAccess(false);
        s.setSupportZoom(false);
        s.setTextZoom(100);
        beranda.addJavascriptInterface(new JembatanBeranda(), JEMBATAN_BERANDA);
        beranda.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                if (r.getUrl().toString().startsWith("file:///android_asset/")) return false;
                bukaLuar(r.getUrl());
                return true;
            }
        });
        beranda.setWebChromeClient(new WebChromeClient());
        akar.addView(beranda, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    /** Panggil window.Beranda.<fungsi>(argumen...) di halaman Beranda. */
    private void keBeranda(final String fungsi, final String argumenJs) {
        runOnUiThread(() -> beranda.evaluateJavascript(
            "window.Beranda&&Beranda." + fungsi + "(" + argumenJs + ")", null));
    }

    private static String kutip(String s) {
        return JSONObject.quote(s == null ? "" : s);
    }

    /** Hanya dipasang di WebView Beranda (halaman lokal), tidak di halaman server. */
    private class JembatanBeranda {
        @JavascriptInterface
        public String info() {
            JSONObject o = new JSONObject();
            try {
                o.put("versi", versiNama());
                o.put("build", versiKode());
                o.put("alamat", pref().getString(KUNCI_ALAMAT, ""));
                o.put("riwayat", new JSONArray(riwayat()));
            } catch (Exception ignored) {
                // JSONObject.put hanya gagal untuk angka NaN
            }
            return o.toString();
        }

        @JavascriptInterface
        public void tes(String teks) {
            tesKoneksi(teks);
        }

        @JavascriptInterface
        public void batalTes() {
            nomorTes.incrementAndGet();
            alamatAktif = "";
        }

        @JavascriptInterface
        public void masuk() {
            runOnUiThread(MainActivity.this::masuk);
        }

        @JavascriptInterface
        public String hapusRiwayat(String a) {
            List<String> d = riwayat();
            d.remove(a);
            simpanRiwayat(d, null);
            return new JSONArray(d).toString();
        }

        @JavascriptInterface
        public void cekPembaruan() {
            MainActivity.this.cekPembaruan();
        }

        @JavascriptInterface
        public void pasang() {
            runOnUiThread(MainActivity.this::unduhDanPasang);
        }

        @JavascriptInterface
        public void bukaRilis() {
            bukaLuar(Uri.parse(Versi.HALAMAN_RILIS));
        }

        @JavascriptInterface
        public void keluar() {
            runOnUiThread(MainActivity.this::keluar);
        }
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

    private void simpanRiwayat(List<String> d, String alamatUtama) {
        StringBuilder sb = new StringBuilder();
        for (String s : d) sb.append(s).append('\n');
        SharedPreferences.Editor e = pref().edit().putString(KUNCI_RIWAYAT, sb.toString());
        if (alamatUtama != null) e.putString(KUNCI_ALAMAT, alamatUtama);
        e.apply();
    }

    private List<String> catatAlamat(String dasar) {
        List<String> d = riwayat();
        d.remove(dasar);
        d.add(0, dasar);
        while (d.size() > MAKS_RIWAYAT) d.remove(d.size() - 1);
        simpanRiwayat(d, dasar);
        return d;
    }

    private void tesKoneksi(String teks) {
        final int nomor = nomorTes.incrementAndGet();
        alamatAktif = "";
        final String[] a = Versi.alamat(teks);
        if (a == null) {
            kirimHasilTes(nomor, false, "mati", "Alamat tidak valid. Contoh: http://192.168.1.10:8090", null, null);
            return;
        }
        new Thread(() -> {
            long mulai = System.currentTimeMillis();
            String st;
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
                        int n;
                        int total = 0;
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
                    st = "ok";
                    pesan = "Server AI Asisten aktif · " + ms + " ms";
                } else if (kode == 200) {
                    st = "peringatan";
                    pesan = "Terhubung, tapi bukan server AI Asisten (port dipakai aplikasi lain?)";
                } else {
                    st = "peringatan";
                    pesan = "Server menjawab kode " + kode + ", bukan halaman AI Asisten";
                }
            } catch (ConnectException e) {
                st = "mati";
                pesan = "Tidak aktif: tidak ada yang menjawab (asisten.py belum jalan?)";
            } catch (SocketTimeoutException e) {
                st = "mati";
                pesan = "Waktu habis: HP dan Pi mungkin beda jaringan";
            } catch (UnknownHostException e) {
                st = "mati";
                pesan = "Nama alamat tidak dikenal";
            } catch (NoRouteToHostException e) {
                st = "mati";
                pesan = "Tidak ada jalur ke alamat ini (beda jaringan?)";
            } catch (Exception e) {
                st = "mati";
                pesan = "Gagal: " + e.getClass().getSimpleName()
                    + (e.getMessage() == null ? "" : " (" + e.getMessage() + ")");
            } finally {
                if (c != null) c.disconnect();
            }
            List<String> daftar = null;
            if (aktif && nomor == nomorTes.get()) {
                alamatAktif = a[0];
                muatLengkap = a[1];
                daftar = catatAlamat(a[0]);
            }
            kirimHasilTes(nomor, aktif, st, pesan, a[0], daftar);
        }).start();
    }

    private void kirimHasilTes(int nomor, boolean aktif, String st, String pesan, String dasar,
                               List<String> daftar) {
        if (nomor != nomorTes.get()) return;   // alamat sudah diganti sejak tes ini dimulai
        JSONObject o = new JSONObject();
        try {
            o.put("aktif", aktif);
            o.put("st", st);
            o.put("pesan", pesan);
            o.put("dasar", dasar == null ? "" : dasar);
            if (daftar != null) o.put("riwayat", new JSONArray(daftar));
        } catch (Exception ignored) {
            // tidak terjadi untuk nilai di atas
        }
        keBeranda("hasilTes", kutip(o.toString()));
    }

    private void masuk() {
        String dasar = alamatAktif;
        if (dasar.isEmpty()) return;
        String url = web.getUrl();
        boolean sudahDimuat = dasar.equals(alamatWeb) && url != null && url.startsWith(dasar)
            && !muatLengkap.contains("?");
        tampilWeb();
        if (!sudahDimuat) {
            alamatWeb = dasar;
            bersihkanRiwayat = true;   // clearHistory baru berlaku setelah halaman baru selesai dimuat
            web.loadUrl(muatLengkap.isEmpty() ? dasar + "/" : muatLengkap);
        }
        muatLengkap = dasar + "/";   // ?token= cukup sekali: halaman menyimpannya sendiri
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
        new Thread(() -> {
            JSONObject o = new JSONObject();
            try {
                Pembaruan.Rilis r = Pembaruan.cekTerbaru();
                if (r == null) {
                    o.put("kosong", true);
                } else if (r.build > versiKode()) {
                    rilisBaru = r;
                    o.put("ada", true);
                    o.put("versi", r.versi);
                    o.put("build", r.build);
                    if (r.ukuran > 0) o.put("kb", Math.max(1, r.ukuran / 1024));
                }
            } catch (Exception e) {
                try {
                    o.put("galat", e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage());
                } catch (Exception ignored) {
                    // tidak terjadi
                }
            }
            keBeranda("hasilPembaruan", kutip(o.toString()));
        }).start();
    }

    private void hasilPasang(String st, String pesan) {
        JSONObject o = new JSONObject();
        try {
            o.put("st", st);
            o.put("pesan", pesan);
        } catch (Exception ignored) {
            // tidak terjadi
        }
        keBeranda("hasilPasang", kutip(o.toString()));
    }

    private void unduhDanPasang() {
        final Pembaruan.Rilis r = rilisBaru;
        if (r == null || sedangUnduh) return;
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            hasilPasang("peringatan", "Perlu izin memasang aplikasi dari sumber ini");
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
        final File f = berkasPembaruan();
        sedangUnduh = true;
        keBeranda("kemajuan", "0," + r.ukuran);
        new Thread(() -> {
            String galat = null;
            try {
                Pembaruan.unduh(r, f, (dapat, total) -> keBeranda("kemajuan", dapat + "," + total));
                Pembaruan.pasang(MainActivity.this, f);
            } catch (Exception e) {
                galat = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            }
            sedangUnduh = false;
            if (galat != null) hasilPasang("mati", "Pembaruan gagal: " + galat);
            else hasilPasang("muat", "Menunggu konfirmasi pemasangan dari Android...");
        }).start();
    }

    /** Hasil PackageInstaller (lihat Pembaruan.pasang). */
    private void tanganiIntent(Intent i) {
        if (i == null || !Pembaruan.AKSI_PASANG.equals(i.getAction())) return;
        int status = i.getIntExtra(PackageInstaller.EXTRA_STATUS, Integer.MIN_VALUE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent konfirmasi = i.getParcelableExtra(Intent.EXTRA_INTENT);
            if (konfirmasi == null) {
                hasilPasang("mati", "Android tidak memberi layar konfirmasi");
                return;
            }
            try {
                startActivity(konfirmasi);
            } catch (Exception e) {
                hasilPasang("mati", "Pemasang Android tidak bisa dibuka");
            }
        } else if (status == PackageInstaller.STATUS_SUCCESS) {
            hasilPasang("ok", "Pembaruan terpasang");
        } else if (status == PackageInstaller.STATUS_FAILURE_ABORTED) {
            hasilPasang("peringatan", "Pemasangan dibatalkan");
        } else if (status != Integer.MIN_VALUE) {
            String pesan = i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            hasilPasang("mati", "Pembaruan gagal: " + (pesan == null ? "kode " + status : pesan));
        }
    }

    /* ============================================================ halaman server */

    private void bangunWeb(FrameLayout akar) {
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

    @SuppressLint("SetJavaScriptEnabled")
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

        web.addJavascriptInterface(new JembatanWeb(), JEMBATAN_WEB);

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
                if (bersihkanRiwayat && url != null && !url.startsWith("about:")) {
                    v.clearHistory();      // halaman server lama / kosong / galat tidak bisa dimundurkan lagi
                    bersihkanRiwayat = false;
                }
                v.evaluateJavascript(JS_UNDUH, null);
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (!r.isForMainFrame()) return;
                // Koneksi putus: kembali ke Beranda dengan pesan, tombol Masuk disembunyikan.
                alamatWeb = "";
                alamatAktif = "";
                bersihkanRiwayat = true;
                v.stopLoading();
                v.loadUrl("about:blank");
                tampilBeranda();
                keBeranda("putus", kutip("Koneksi terputus: " + e.getDescription()
                    + ". Tekan Tes koneksi untuk mencoba lagi."));
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
                    + JEMBATAN_WEB + ".simpan(s.substring(s.indexOf(',')+1),'"
                    + nama.replace("'", "") + "',b.type||'');};f.readAsDataURL(b);})", null);
            } else {
                bukaLuar(Uri.parse(url));
            }
        });
    }

    private void bukaLuar(Uri u) {
        runOnUiThread(() -> {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, u));
            } catch (ActivityNotFoundException e) {
                pesan("Tidak ada aplikasi untuk membuka: " + u);
            }
        });
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

    /* ------------------------------------------------------------ unduhan dari halaman server */

    /** Dipasang di halaman server: hanya untuk menyimpan unduhan dan menampilkan pesan. */
    private class JembatanWeb {
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
