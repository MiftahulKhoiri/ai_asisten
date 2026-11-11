package id.aiasisten.app;

import java.net.URI;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Fungsi murni tanpa API Android (diuji di Pi/CI dengan Java biasa: android/uji/UjiVersi.java). */
final class Versi {
    static final String REPO = "MiftahulKhoiri/ai_asisten";
    static final String AWALAN_TAG = "android-v";
    static final String HALAMAN_RILIS = "https://github.com/" + REPO + "/releases";

    private static final Pattern BUILD = Pattern.compile("-build(\\d+)\\.apk$");

    private Versi() {
    }

    /** "AI-Asisten-v1.1.0-build280.apk" -> 280 (sama dengan versionCode). -1 bila tidak cocok. */
    static int buildDariNama(String nama) {
        if (nama == null) return -1;
        Matcher m = BUILD.matcher(nama);
        if (!m.find()) return -1;
        try {
            return Integer.parseInt(m.group(1));
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    /** "android-v1.1.0" -> "1.1.0". */
    static String versiDariTag(String tag) {
        if (tag == null) return "";
        return tag.startsWith(AWALAN_TAG) ? tag.substring(AWALAN_TAG.length()) : tag;
    }

    /** "sha256:abc..." -> "abc..." (huruf kecil); selain itu "". */
    static String sha256DariDigest(String digest) {
        if (digest == null || !digest.startsWith("sha256:")) return "";
        return digest.substring(7).trim().toLowerCase();
    }

    /**
     * Rapikan isian alamat server. Hasil {dasar, lengkap} atau null bila tidak valid.
     * dasar   = http://host:port (disimpan)
     * lengkap = dasar + path + ?query (dimuat sekali, misalnya membawa ?token=...)
     */
    static String[] alamat(String teks) {
        if (teks == null) return null;
        String t = teks.trim();
        if (t.isEmpty() || t.equals("http://") || t.equals("https://")) return null;
        if (!t.startsWith("http://") && !t.startsWith("https://")) t = "http://" + t;
        URI u;
        try {
            u = new URI(t);
        } catch (Exception e) {
            return null;
        }
        String host = u.getHost();
        String skema = u.getScheme();
        if (host == null || host.isEmpty() || skema == null) return null;
        String dasar = skema.toLowerCase() + "://" + host + (u.getPort() > 0 ? ":" + u.getPort() : "");
        String path = u.getRawPath();
        String q = u.getRawQuery();
        String lengkap = dasar + (path == null || path.isEmpty() ? "/" : path) + (q == null ? "" : "?" + q);
        return new String[]{dasar, lengkap};
    }

    /** Halaman awal server ai_asisten memuat dasbor.js; dipakai untuk membedakan dari server lain. */
    static boolean halamanAiAsisten(String isi) {
        return isi != null && (isi.contains("dasbor.js") || isi.contains("AI Asisten"));
    }
}
