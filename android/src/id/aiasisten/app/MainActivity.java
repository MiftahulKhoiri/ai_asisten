package id.aiasisten.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.InputType;
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
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * AI Asisten untuk Android: membuka halaman web asisten.py di WebView, jadi tampilannya persis sama
 * dengan di browser dan otomatis ikut berubah kalau berkas web/ di server diperbarui.
 *
 * Tambahan yang tidak dimiliki WebView biasa:
 *  - alamat server disimpan (pertama kali ditanya; boleh ditempel lengkap dengan ?token=...)
 *  - unggah berkas (input type=file, bisa banyak berkas)
 *  - unduhan blob dari halaman (ekspor prompt .json, hasil Agent .zip) disimpan ke Download/AI Asisten
 *  - dialog alert/confirm/prompt, tautan luar dibuka di browser, tombol kembali, layar galat koneksi
 */
public class MainActivity extends Activity {

    private static final String PREF = "pengaturan";
    private static final String KUNCI_ALAMAT = "alamat";
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

    private WebView web;
    private ProgressBar bilah;
    private LinearLayout layarGalat;
    private TextView teksGalat;
    private boolean galat;
    private String alamat = "";          // http://host:port tanpa path/query
    private ValueCallback<Uri[]> panggilBerkas;
    private boolean gelap;
    private int warnaLatar;

    @Override
    protected void onCreate(Bundle simpanan) {
        super.onCreate(simpanan);
        gelap = Build.VERSION.SDK_INT < 29
            || (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
               == Configuration.UI_MODE_NIGHT_YES;
        warnaLatar = gelap ? 0xFF111317 : 0xFFF4F5F7;
        aturBilahSistem();
        bangunTampilan();
        aturWeb();

        alamat = pref().getString(KUNCI_ALAMAT, "");
        if (simpanan != null && web.restoreState(simpanan) != null) {
            return;
        }
        if (alamat.isEmpty()) {
            tanyaAlamat(true);
        } else {
            web.loadUrl(alamat + "/");
        }
    }

    /* ------------------------------------------------------------ tampilan */

    private int dp(float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v,
            getResources().getDisplayMetrics()));
    }

    @SuppressWarnings("deprecation")
    private void aturBilahSistem() {
        Window w = getWindow();
        w.setStatusBarColor(warnaLatar);
        w.setNavigationBarColor(warnaLatar);
        if (!gelap) {
            int f = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 26) f |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            w.getDecorView().setSystemUiVisibility(f);
        }
    }

    private void bangunTampilan() {
        FrameLayout akar = new FrameLayout(this);
        akar.setBackgroundColor(warnaLatar);

        web = new WebView(this);
        web.setBackgroundColor(warnaLatar);
        akar.addView(web, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        bilah = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bilah.setMax(100);
        bilah.setVisibility(View.GONE);
        FrameLayout.LayoutParams lpBilah = new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(3), Gravity.TOP);
        akar.addView(bilah, lpBilah);

        int warnaTeks = gelap ? 0xFFE6E8EC : 0xFF1B1F27;
        int warnaRedup = gelap ? 0xFF8B93A1 : 0xFF6B7280;

        layarGalat = new LinearLayout(this);
        layarGalat.setOrientation(LinearLayout.VERTICAL);
        layarGalat.setGravity(Gravity.CENTER);
        layarGalat.setPadding(dp(28), dp(28), dp(28), dp(28));
        layarGalat.setVisibility(View.GONE);

        TextView judul = new TextView(this);
        judul.setText("Tidak bisa terhubung");
        judul.setTextColor(warnaTeks);
        judul.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        judul.setTypeface(Typeface.DEFAULT_BOLD);
        judul.setGravity(Gravity.CENTER);
        layarGalat.addView(judul);

        teksGalat = new TextView(this);
        teksGalat.setTextColor(warnaRedup);
        teksGalat.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        teksGalat.setGravity(Gravity.CENTER);
        teksGalat.setPadding(0, dp(12), 0, dp(20));
        layarGalat.addView(teksGalat);

        LinearLayout tombol = new LinearLayout(this);
        tombol.setOrientation(LinearLayout.HORIZONTAL);
        tombol.setGravity(Gravity.CENTER);
        Button ulang = new Button(this);
        ulang.setText("Coba lagi");
        ulang.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { cobaLagi(); }
        });
        Button ubah = new Button(this);
        ubah.setText("Ubah alamat");
        ubah.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { tanyaAlamat(false); }
        });
        tombol.addView(ulang);
        tombol.addView(ubah);
        layarGalat.addView(tombol);

        akar.addView(layarGalat, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(akar);
    }

    private void tampilGalat(String pesan) {
        galat = true;
        web.setVisibility(View.INVISIBLE);
        bilah.setVisibility(View.GONE);
        teksGalat.setText("Server: " + (alamat.isEmpty() ? "(belum diisi)" : alamat)
            + "\n" + pesan
            + "\n\nPastikan asisten.py sedang berjalan dan HP satu jaringan dengan Pi "
            + "(Wi-Fi yang sama atau Tailscale).");
        layarGalat.setVisibility(View.VISIBLE);
    }

    private void cobaLagi() {
        galat = false;
        layarGalat.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
        String u = web.getUrl();
        if (u == null || u.isEmpty() || u.startsWith("data:") || u.startsWith("about:")) {
            web.loadUrl(alamat + "/");
        } else {
            web.reload();
        }
    }

    /* ------------------------------------------------------------ alamat server */

    private SharedPreferences pref() {
        return getSharedPreferences(PREF, Context.MODE_PRIVATE);
    }

    private void tanyaAlamat(final boolean pertama) {
        final EditText isian = new EditText(this);
        isian.setSingleLine(true);
        isian.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        isian.setHint("http://192.168.1.10:8090");
        isian.setText(alamat.isEmpty() ? "http://" : alamat);
        isian.setSelection(isian.getText().length());
        FrameLayout bungkus = new FrameLayout(this);
        bungkus.setPadding(dp(22), dp(4), dp(22), 0);
        bungkus.addView(isian);

        AlertDialog.Builder b = new AlertDialog.Builder(this)
            .setTitle("Alamat server AI Asisten")
            .setMessage("Isi alamat yang tampil di terminal saat asisten.py dijalankan. "
                + "Boleh ditempel lengkap dengan ?token=... supaya token langsung tersimpan.")
            .setView(bungkus)
            .setPositiveButton("Simpan", null)
            .setCancelable(!pertama);
        if (!pertama) b.setNegativeButton("Batal", null);
        final AlertDialog d = b.create();
        d.setOnShowListener(new android.content.DialogInterface.OnShowListener() {
            @Override public void onShow(android.content.DialogInterface di) {
                d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(new View.OnClickListener() {
                    @Override public void onClick(View v) {
                        String hasil = simpanAlamat(isian.getText().toString());
                        if (hasil == null) {
                            isian.setError("Alamat tidak valid, contoh: http://192.168.1.10:8090");
                            return;
                        }
                        d.dismiss();
                        galat = false;
                        layarGalat.setVisibility(View.GONE);
                        web.setVisibility(View.VISIBLE);
                        web.loadUrl(hasil);
                    }
                });
            }
        });
        d.show();
    }

    /** Simpan http://host:port; kembalikan alamat lengkap yang dimuat (beserta path/?token=), atau null. */
    private String simpanAlamat(String teks) {
        String t = teks.trim();
        if (t.isEmpty() || t.equals("http://") || t.equals("https://")) return null;
        if (!t.startsWith("http://") && !t.startsWith("https://")) t = "http://" + t;
        Uri u = Uri.parse(t);
        String host = u.getHost();
        if (host == null || host.isEmpty()) return null;
        String dasar = u.getScheme() + "://" + (host.contains(":") ? "[" + host + "]" : host)
            + (u.getPort() > 0 ? ":" + u.getPort() : "");
        alamat = dasar;
        pref().edit().putString(KUNCI_ALAMAT, dasar).apply();
        String path = u.getEncodedPath();
        String q = u.getEncodedQuery();
        return dasar + (path == null || path.isEmpty() ? "/" : path) + (q == null ? "" : "?" + q);
    }

    private boolean sesamaServer(Uri u) {
        if (alamat.isEmpty()) return true;
        Uri a = Uri.parse(alamat);
        return a.getHost() != null && a.getHost().equalsIgnoreCase(u.getHost())
            && a.getPort() == u.getPort();
    }

    /* ------------------------------------------------------------ WebView */

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
        s.setUserAgentString(s.getUserAgentString() + " AiAsistenAndroid/" + versi());

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
                bilah.setProgress(5);
                bilah.setVisibility(View.VISIBLE);
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                bilah.setVisibility(View.GONE);
                v.evaluateJavascript(JS_UNDUH, null);
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) tampilGalat(String.valueOf(e.getDescription()));
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView v, int p) {
                bilah.setProgress(Math.max(5, p));
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

    private String versi() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
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

    /* ------------------------------------------------------------ unduhan */

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

    /* ------------------------------------------------------------ siklus hidup */

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (!galat && web.canGoBack()) {
            web.goBack();
            return;
        }
        String[] pilihan = {"Muat ulang", "Ubah alamat server", "Keluar"};
        new AlertDialog.Builder(this)
            .setTitle("AI Asisten")
            .setItems(pilihan, (d, i) -> {
                if (i == 0) cobaLagi();
                else if (i == 1) tanyaAlamat(false);
                else finish();
            })
            .setNegativeButton("Batal", null)
            .show();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
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
}
