"""pengaman.py - pengaman perintah shell (daftar blokir dan daftar wajib izin)."""

import re


# Perintah yang SELALU diblokir, bahkan dalam mode AUTO, dan perintah yang SELALU
# minta konfirmasi walau mode AUTO aktif (lihat cek_perintah di bawah).
_AKAR = (r"(?:/|/\*|~/?|~/\*|\$HOME/?|\$HOME/\*|\$\{HOME\}/?|\$\{HOME\}/\*)")
_SISTEM = (r"/(?:etc|usr|boot|bin|sbin|lib|lib32|lib64|var|home|root|sys|proc|dev|"
           r"opt|srv|mnt|media)/?\*?")
_UJUNG = r"(?=\s|$|[;&|)<>])"
_ARG = r"[^\s;&|]+"            # satu argumen, tidak melewati pemisah perintah
# awal perintah: di awal teks/baris, setelah pemisah, atau setelah sudo/xargs/env/dst
_AWAL = (r"(?:^|[;&|({`\n]\s*|\b(?:sudo|xargs|nohup|env|time|command|exec|builtin)"
         r"\s+(?:-\S+\s+)*)")
_TARGET = r"(?:" + _AKAR + r"|" + _SISTEM + r")" + _UJUNG


BAHAYA = [
    r"\brm\s+(?:" + _ARG + r"\s+)*?" + _TARGET,
    r"\bmv\s+(?:-\S+\s+)*" + _TARGET,
    r"\bfind\s+(?:-\S+\s+)*" + _AKAR + _UJUNG + r"[^;&|]*(?:-delete\b|-exec(?:dir)?\s+\S*\brm\b)",
    r"\b(?:chmod|chown)\s+(?:" + _ARG + r"\s+)*?-\S*R\S*\s+(?:" + _ARG + r"\s+)*?" + _TARGET,
    r"\bmkfs(\.\w+)?\b",
    r"\bwipefs\b",
    r"\bshred\s+(?:-\S+\s+)*/dev/",
    r"\bdd\b.*\bof=/dev/",
    r">\s*/dev/(sd|nvme|mmcblk)",
    r"\btee\s+(?:-\S+\s+)*/dev/(?:sd|nvme|mmcblk)",
    r":\(\)\s*\{",
    r"\b(shutdown|reboot|poweroff|halt)\b",
    r"\b(?:init|telinit)\s+[06]\b",
    r"\bkillall5\b",
    r"\b(?:kill|pkill)\s+(?:-\S+\s+)*-1\s*(?:$|[;&|])",
    r"\bgit\b[^;&|]*\bpush\b[^;&|]*\s(?:--force\b|--force-with-lease\b|-f\b|--delete\b)",
    r"\bgit\b[^;&|]*\breset\b[^;&|]*\s--hard\b",
    r"\bgit\b[^;&|]*\bclean\b[^;&|]*\s-\S*f",
]


# ---- Pola tambahan untuk KONFIRMASI_SELALU (mode AUTO tetap bertanya) -------------------
# Interpreter yang menjalankan kode dari teks perintah itu sendiri (-c, -e, heredoc, pipa).
_INTERP = r"(?:python[\d.]*|pypy\d*|perl|ruby|lua|php|node(?:js)?|bun|deno)"
# File rahasia: dibaca lewat shell (cat ~/.ssh/id_x, grep KEY .env, tar ... ~/.aws).
_RAHASIA_SHELL = (
    r"(?:\.ssh/(?!known_hosts|config\b|\S*\.pub)\S|\.token\b|\.git-credentials|\.netrc\b|"
    r"\.pgpass|\.aws(?:/|(?=\s|$))|\.gnupg\b|\.kube/config|\.config/gh/|\.docker/config\.json|"
    r"ai_asisten\.env|/etc/shadow|/etc/sudoers|\.(?:bash|zsh|python)_history|"
    r"(?<![\w.-])\.env(?:\.(?!example|sample|template|dist)\w+)?(?=\s|$|[;&|)<>]))")
_BACA = (r"(?:\b(?:cat|tac|nl|less|more|head|tail|bat|cp|mv|scp|rsync|curl|wget|base64|xxd|od|"
         r"hexdump|strings|grep|egrep|fgrep|rg|ag|awk|sed|cut|sort|uniq|tar|zip|7z|gzip|source|"
         r"export)\b|(?:^|[;&|(`\n]\s*)\.(?=\s))")
# Skrip login, unit systemd/autostart, ~/.local/bin, .git/hooks: tempat menanam persistensi.
_STARTUP = (
    r"(?:(?<![\w.-])\.(?:bashrc|bash_profile|bash_login|bash_logout|profile|zshrc|zprofile|"
    r"zshenv|zlogin|xprofile|xsession|pam_environment|inputrc|gitconfig)(?![\w.-])|"
    r"\.config/(?:systemd|autostart|environment\.d|git)/|\.ssh/authorized_keys|\.git/hooks/|"
    r"\.local/bin/|(?:~|\$HOME|\$\{HOME\})/bin/)")
_TULIS = (r"(?:>|\b(?:tee|cp|mv|ln|truncate|install|rsync|"
          r"(?:sed|perl)\s+(?:-\S+\s+)*-\S*i\S*)\b)")


KONFIRMASI_SELALU = [
    r"\bsudo\b",
    r"\b(?:apt|apt-get)\s+(?:-\S+\s+)*(?:install|remove|purge|upgrade|dist-upgrade|"
    r"full-upgrade|autoremove|autopurge)\b",
    r"\b(?:dpkg|pip3?|pipx|snap)\s+(?:-\S+\s+)*(?:install|remove|purge|uninstall|upgrade|-i|-r|-P)\b",
    r"\b(?:npm|yarn|pnpm)\s+(?:-\S+\s+)*(?:i|install|add|remove|rm|uninstall|un|update|upgrade)\b",
    _AWAL + r"(?:\S*/)?(?:rm|shred|unlink)(?=\s|$)",
    r"\bfind\b[^;&|]*(?:-delete\b|-exec(?:dir)?\s+\S*\b(?:rm|shred|dd|mv)\b)",
    r"\b(?:chmod|chown)\b[^;&|]*\s-\S*R",
    r"\b(?:kill|pkill|killall)\b(?!\s+-l\b)",
    r"\bgit\b[^;&|]*\bpush\b",
    r"\|\s*(?:sudo\s+)?(?:env\s+)?(?:\S*/)?(?:ba|da|z|k|a)?sh(?=\s|$|[;&|)])",
    r"(?:\$\(|<\(|`)\s*(?:curl|wget)\b",
    r"\b(?:ba|da|z|k|a)?sh\s+(?:-\S+\s+)*-\S*c\b",
    r"\beval\b",
    r"\bsource\s+<\(",
    r"\bbase64\b[^;&|]*\s(?:-d|-D|--decode)\b",
    # --- kode inline lewat interpreter ---
    r"\b" + _INTERP + r"\s+(?:-\S+\s+)*(?:-[A-Za-z]*[cerE]\S*|--(?:eval|print|command)\b)",
    r"\b" + _INTERP + r"\b(?:\s+-)?\s*<(?!\()",           # heredoc / < file
    r"\|\s*(?:sudo\s+)?(?:\S*/)?" + _INTERP + r"(?:\s+-)?(?=\s*(?:$|[;&|)]))",   # ... | python3
    # --- baca file rahasia lewat shell ---
    _BACA + r"[^;&|\n]*" + _RAHASIA_SHELL,
    r"<\s*\S*" + _RAHASIA_SHELL,
    # --- persistensi: skrip login, cron, systemd, soket balik ---
    _TULIS + r"[^;&|\n]*" + _STARTUP,
    r"\bcrontab\b(?!\s+-l\b)",
    r"\bsystemctl\b[^;&|\n]*\b(?:enable|disable|start|stop|restart|reload|mask|unmask|link|edit|"
    r"set-default|daemon-reload|kill|reset-failed)\b",
    r"\bsystemd-run\b",
    r"\bloginctl\b[^;&|\n]*\b(?:enable-linger|disable-linger|terminate-\w+|kill-\w+)\b",
    r"\b(?:nc|ncat|netcat|socat)\b[^;&|\n]*\s(?:-\w*[ec]\b|--(?:exec|sh-exec)\b|EXEC:|exec:)",
    r"/dev/(?:tcp|udp)/",
]


def _normal(p):
    p = p.replace("${IFS}", " ").replace("$IFS", " ")
    p = re.sub(r"[\\'\"]", "", p)
    return re.sub(r"\s+", " ", p)


def cek_perintah(perintah):
    """'blokir' (selalu ditolak), 'izin' (selalu tanya, juga di mode AUTO), atau None.

    Dicocokkan pada teks asli dan teks yang tanda kutip/backslash-nya dibuang, supaya
    `bash -c 'rm -rf /'` atau `r\\m -rf /` tidak lolos. Ini pengaman dasar berbasis pola:
    variabel, brace expansion, atau `python -c` tetap bisa menyamarkan perintah.
    """
    kand = (perintah, _normal(perintah))
    if any(re.search(p, k) for p in BAHAYA for k in kand):
        return "blokir"
    if any(re.search(p, k) for p in KONFIRMASI_SELALU for k in kand):
        return "izin"
    return None
