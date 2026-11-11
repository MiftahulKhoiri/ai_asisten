package id.aiasisten.app;

/** Uji fungsi murni Versi dengan Java biasa (tanpa Android). Dijalankan otomatis oleh build.sh. */
public final class UjiVersi {
    private static int gagal;

    private static void cek(boolean ok, String nama) {
        System.out.println((ok ? "  lulus  " : "  GAGAL  ") + nama);
        if (!ok) gagal++;
    }

    private static boolean sama(String[] a, String dasar, String lengkap) {
        return a != null && a[0].equals(dasar) && a[1].equals(lengkap);
    }

    public static void main(String[] args) {
        cek(Versi.buildDariNama("AI-Asisten-v1.1.0-build280.apk") == 280, "build dari nama APK");
        cek(Versi.buildDariNama("AI-Asisten-v1.1.0.apk") == -1, "nama tanpa build -> -1");
        cek(Versi.buildDariNama("catatan-build3.txt") == -1, "bukan .apk -> -1");
        cek(Versi.buildDariNama(null) == -1, "null -> -1");
        cek(Versi.versiDariTag("android-v1.2.3").equals("1.2.3"), "versi dari tag");
        cek(Versi.versiDariTag("v9").equals("v9"), "tag lain apa adanya");
        cek(Versi.sha256DariDigest("sha256:ABCdef").equals("abcdef"), "digest sha256");
        cek(Versi.sha256DariDigest("md5:x").isEmpty(), "digest lain -> kosong");

        cek(sama(Versi.alamat("192.168.1.10:8090"), "http://192.168.1.10:8090", "http://192.168.1.10:8090/"),
            "alamat tanpa skema");
        cek(sama(Versi.alamat(" http://192.168.1.10:8090/?token=AbC_1 "), "http://192.168.1.10:8090",
            "http://192.168.1.10:8090/?token=AbC_1"), "alamat dengan token");
        cek(sama(Versi.alamat("https://pi.local/chat"), "https://pi.local", "https://pi.local/chat"),
            "https dengan path");
        cek(sama(Versi.alamat("http://[fd7a::1]:8090"), "http://[fd7a::1]:8090", "http://[fd7a::1]:8090/"),
            "IPv6");
        cek(Versi.alamat("") == null, "kosong -> null");
        cek(Versi.alamat("http://") == null, "hanya skema -> null");
        cek(Versi.alamat("http://ada spasi:80") == null, "spasi -> null");

        cek(Versi.halamanAiAsisten("<script src=\"dasbor.js\"></script>"), "kenali halaman AI Asisten");
        cek(!Versi.halamanAiAsisten("<title>Game Server</title>"), "tolak server lain");

        if (gagal > 0) {
            System.out.println(gagal + " uji gagal");
            System.exit(1);
        }
        System.out.println("semua uji Versi lulus");
    }
}
