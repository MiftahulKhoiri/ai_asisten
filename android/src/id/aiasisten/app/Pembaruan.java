package id.aiasisten.app;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * Pembaruan dari dalam aplikasi, mengikuti pola Game_server:
 *   1. baca rilis terbaru bertag android-v* dari GitHub Releases
 *   2. unduh APK, periksa ukuran dan sha256 (dari kolom digest GitHub)
 *   3. pasang lewat PackageInstaller; Android menampilkan konfirmasi "Perbarui"
 * Semua fungsi jaringan memblokir: panggil dari thread latar.
 */
final class Pembaruan {
    static final String AKSI_PASANG = "id.aiasisten.app.HASIL_PASANG";
    private static final String UA = "AiAsistenAndroid";

    static final class Rilis {
        String tag = "";
        String versi = "";
        String nama = "";
        String url = "";
        String sha256 = "";
        long ukuran;
        int build = -1;
    }

    interface Kemajuan {
        void kabar(long dapat, long total);
    }

    private Pembaruan() {
    }

    /** Rilis android-v* terbaru yang memuat APK, atau null bila belum ada. */
    static Rilis cekTerbaru() throws Exception {
        JSONArray daftar = new JSONArray(ambilTeks(
            "https://api.github.com/repos/" + Versi.REPO + "/releases?per_page=30"));
        for (int i = 0; i < daftar.length(); i++) {
            JSONObject r = daftar.getJSONObject(i);
            if (r.optBoolean("draft") || r.optBoolean("prerelease")) continue;
            String tag = r.optString("tag_name", "");
            if (!tag.startsWith(Versi.AWALAN_TAG)) continue;
            JSONArray aset = r.optJSONArray("assets");
            if (aset == null) continue;
            for (int j = 0; j < aset.length(); j++) {
                JSONObject a = aset.getJSONObject(j);
                String nama = a.optString("name", "");
                int build = Versi.buildDariNama(nama);
                String url = a.optString("browser_download_url", "");
                if (build < 0 || url.isEmpty()) continue;
                Rilis h = new Rilis();
                h.tag = tag;
                h.versi = Versi.versiDariTag(tag);
                h.nama = nama;
                h.url = url;
                h.build = build;
                h.ukuran = a.optLong("size", 0);
                h.sha256 = Versi.sha256DariDigest(a.optString("digest", ""));
                return h;
            }
        }
        return null;
    }

    private static HttpURLConnection buka(String url, int batasMs) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(batasMs);
        c.setReadTimeout(batasMs);
        c.setInstanceFollowRedirects(true);
        c.setRequestProperty("User-Agent", UA);
        return c;
    }

    private static String ambilTeks(String url) throws Exception {
        HttpURLConnection c = buka(url, 10000);
        c.setRequestProperty("Accept", "application/vnd.github+json");
        try {
            int kode = c.getResponseCode();
            if (kode == 403 || kode == 429) throw new Exception("batas akses GitHub tercapai, coba lagi nanti");
            if (kode != 200) throw new Exception("GitHub menjawab kode " + kode);
            try (InputStream in = c.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[16384];
                int n;
                while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                return out.toString("UTF-8");
            }
        } finally {
            c.disconnect();
        }
    }

    /** Unduh APK rilis ke `tujuan` lalu periksa ukuran dan sha256. Gagal -> berkas dihapus. */
    static void unduh(Rilis r, File tujuan, Kemajuan k) throws Exception {
        HttpURLConnection c = buka(r.url, 20000);
        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        long dapat = 0;
        try {
            int kode = c.getResponseCode();
            if (kode != 200) throw new Exception("unduhan gagal, kode " + kode);
            long total = r.ukuran > 0 ? r.ukuran : c.getContentLength();
            try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(tujuan)) {
                byte[] buf = new byte[65536];
                int n;
                long kabarTerakhir = 0;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                    sha.update(buf, 0, n);
                    dapat += n;
                    if (dapat - kabarTerakhir > 32768 || dapat == total) {
                        kabarTerakhir = dapat;
                        k.kabar(dapat, total);
                    }
                }
            }
        } catch (Exception e) {
            //noinspection ResultOfMethodCallIgnored
            tujuan.delete();
            throw e;
        } finally {
            c.disconnect();
        }
        String salah = null;
        if (dapat < 1024) salah = "berkas unduhan terlalu kecil";
        else if (r.ukuran > 0 && dapat != r.ukuran) salah = "ukuran berkas tidak cocok (" + dapat + " dari " + r.ukuran + " byte)";
        else if (!r.sha256.isEmpty() && !r.sha256.equals(hex(sha.digest()))) salah = "sidik jari sha256 tidak cocok";
        if (salah != null) {
            //noinspection ResultOfMethodCallIgnored
            tujuan.delete();
            throw new Exception(salah);
        }
    }

    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder(b.length * 2);
        for (byte x : b) s.append(String.format("%02x", x & 0xff));
        return s.toString();
    }

    /** Serahkan APK ke PackageInstaller. Hasilnya datang ke MainActivity.onNewIntent (AKSI_PASANG). */
    static void pasang(Activity a, File apk) throws Exception {
        PackageInstaller pi = a.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams p =
            new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        p.setAppPackageName(a.getPackageName());
        p.setSize(apk.length());
        int id = pi.createSession(p);
        PackageInstaller.Session s = pi.openSession(id);
        try {
            try (OutputStream out = s.openWrite("ai_asisten.apk", 0, apk.length());
                 InputStream in = new FileInputStream(apk)) {
                byte[] buf = new byte[65536];
                int n;
                while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                s.fsync(out);
            }
            Intent i = new Intent(a, MainActivity.class).setAction(AKSI_PASANG);
            int bendera = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 31) bendera |= PendingIntent.FLAG_MUTABLE; // sistem mengisi status
            PendingIntent pin = PendingIntent.getActivity(a, id, i, bendera);
            s.commit(pin.getIntentSender());
        } catch (Exception e) {
            s.abandon();
            throw e;
        } finally {
            try {
                s.close();
            } catch (Exception ignored) {
                // sesi yang sudah dibatalkan/diserahkan boleh gagal ditutup
            }
        }
    }
}
