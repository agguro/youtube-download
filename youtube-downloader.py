#!/usr/bin/env python3
import argparse
from pathlib import Path
from yt_dlp import YoutubeDL
import sys
import shutil
import threading
import subprocess
import os
from datetime import datetime
from typing import List, Dict, Any


# ----------------------------
# Helpers
# ----------------------------
def auto_update_yt_dlp(enable: bool) -> None:
    """
    If enabled, pip-updates yt-dlp. If an update is installed, re-execs the script
    once so the current run benefits from the new version. Guarded by env var to
    avoid loops.
    """
    if not enable:
        return
    if os.environ.get("YTDLP_UPDATED") == "1":
        return
    try:
        print("[*] Checking for yt-dlp updates…")
        # You can add --quiet to make it silent; keeping default for visibility
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if res.returncode == 0:
            # If anything was changed, pip typically prints 'Successfully installed' or 'Successfully upgraded'
            changed = ("Successfully installed" in res.stdout) or ("Successfully installed" in res.stderr) \
                      or ("Successfully upgraded" in res.stdout) or ("Successfully upgraded" in res.stderr)
            if changed:
                print("[*] yt-dlp updated. Restarting once to use the new version…")
                env = dict(os.environ, YTDLP_UPDATED="1")
                os.execvpe(sys.executable, [sys.executable] + sys.argv, env)
        else:
            print("[!] yt-dlp auto-update failed (continuing with current version).", file=sys.stderr)
    except Exception as e:
        print(f"[!] yt-dlp auto-update error: {e}", file=sys.stderr)


def read_links_from_file(path: Path) -> List[str]:
    links: List[str] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                links.append(s)
    except FileNotFoundError:
        print(f"[!] Bestand niet gevonden: {path}", file=sys.stderr)
        sys.exit(1)
    return links


def ensure_dirs(video_dir: Path, music_dir: Path) -> None:
    video_dir.mkdir(parents=True, exist_ok=True)
    music_dir.mkdir(parents=True, exist_ok=True)


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


# ----------------------------
# Global counters and hooks
# ----------------------------
counter = {
    "done": 0,
    "failed": 0,
    "total": 0,
}
logfile_path: Path = None

def write_log(line: str) -> None:
    """Append a line to the logfile (if set)."""
    if logfile_path is None:
        return
    try:
        with logfile_path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        pass


def _on_progress(d: Dict[str, Any]) -> None:
    if d.get("status") == "finished":
        counter["done"] += 1
        fn = d.get("filename") or d.get("info_dict", {}).get("_filename")
        msg = f"({counter['done']}/{counter['total']}) ✓ Finished: {fn}"
        print(msg)
        write_log(msg)


# ----------------------------
# yt-dlp options
# ----------------------------

def _common_opts(allow_playlists: bool) -> Dict[str, Any]:
    return {
        "noplaylist": not allow_playlists,
        "force_overwrites": True,
        "ignoreerrors": "only_download",
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 1,
        "noprogress": True,
        "quiet": True,
        "nocheckcertificate": True,
        "progress_hooks": [_on_progress],
    }


def build_audio_opts(music_dir: Path, allow_playlists: bool) -> Dict[str, Any]:
    opts = _common_opts(allow_playlists)
    opts.update({
        "outtmpl": str(
            music_dir / "%(artist,replace=\" \",\"_\")s-%(title,replace=\" \",\"_\")s.%(ext)s"
        ),
        "outtmpl_na_placeholder": "unknown",
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "0",
        }],
        "restrictfilenames": True,
    })
    return opts


def build_video_opts(video_dir: Path, allow_playlists: bool) -> Dict[str, Any]:
    opts = _common_opts(allow_playlists)
    opts.update({
        "outtmpl": str(
            video_dir / "%(artist,replace=\" \",\"_\")s-%(title,replace=\" \",\"_\")s.%(ext)s"
        ),
        "outtmpl_na_placeholder": "unknown",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "restrictfilenames": True,
    })
    return opts


# ----------------------------
# Debug helpers
# ----------------------------

def print_non_main_threads() -> None:
    main_ident = threading.main_thread().ident
    others = [t for t in threading.enumerate() if t.ident != main_ident]
    if not others:
        print("[debug] Geen extra threads actief.")
        return
    print("[debug] Actieve threads na afloop:")
    for t in others:
        print(f"  - name={t.name!r} daemon={t.daemon} alive={t.is_alive()} class={t.__class__.__name__}")


# ----------------------------
# Main
# ----------------------------

def main() -> None:
    global logfile_path

    home = Path.home()
    default_videos = home / "Videos"
    default_music = home / "Music"

    parser = argparse.ArgumentParser(
        description="Download YouTube-links als video (mp4), audio (m4a) of beide."
    )
    parser.add_argument("-v", "--video", action="store_true",
                        help="Download video (MP4) naar ~/Videos")
    parser.add_argument("-a", "--audio", action="store_true",
                        help="Download audio (M4A) naar ~/Music")
    parser.add_argument("-f", "--file", type=str,
                        help="Bestand met links (één per regel)")
    parser.add_argument("--video-dir", type=str, default=str(default_videos),
                        help="Doelmap voor video's (default: ~/Videos)")
    parser.add_argument("--music-dir", type=str, default=str(default_music),
                        help="Doelmap voor audio (default: ~/Music)")
    parser.add_argument("--allow-playlists", action="store_true",
                        help="Sta playlist-downloads toe (standaard uit).")
    parser.add_argument("--hard-exit", action="store_true",
                        help="Verlaat het proces direct met os._exit() (fix voor hangende threads).")
    parser.add_argument("--debug-threads", action="store_true",
                        help="Print actieve threads bij afsluiten voor diagnose.")
    parser.add_argument("urls", nargs="*", help="YouTube URL(s) of playlist(s)")
    
    parser.add_argument("--auto-update", action="store_true", help="Voer voor start 'pip install -U yt-dlp' uit en herstart 1x indien geüpdatet.")

    args = parser.parse_args()

    auto_update_yt_dlp(args.auto_update)
    
    want_video = args.video or (not args.video and not args.audio)
    want_audio = args.audio or (not args.video and not args.audio)

    # Links verzamelen
    urls: List[str] = []
    if args.file:
        urls.extend(read_links_from_file(Path(args.file)))
    if args.urls:
        urls.extend(args.urls)

    seen = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]

    if not urls:
        print("[!] Geen links opgegeven. Gebruik -f / pad/naar/links.txt of geef URL(s) mee op de commandline.", file=sys.stderr)
        parser.print_help()
        sys.exit(2)

    counter["total"] = len(urls)

    video_dir = Path(args.video_dir).expanduser()
    music_dir = Path(args.music_dir).expanduser()
    ensure_dirs(video_dir, music_dir)

    # Choose log file path
    if want_video:
        logfile_path = video_dir / "download_log.txt"
    elif want_audio:
        logfile_path = music_dir / "download_log.txt"

    write_log(f"\n=== Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    write_log(f"URLs: {len(urls)}")

    if (want_audio or want_video) and not have_ffmpeg():
        print("[!] ffmpeg niet gevonden. Installeer ffmpeg voor audio-extractie en muxen (bijv. apt install ffmpeg).", file=sys.stderr)

    exit_code = 0

    # AUDIO
    if want_audio:
        print(f"[*] Download AUDIO → {music_dir} ({len(urls)} bestanden)")
        a_opts = build_audio_opts(music_dir, allow_playlists=args.allow_playlists)
        try:
            with YoutubeDL(a_opts) as ydl:
                ret = ydl.download(urls)
                if ret != 0:
                    counter["failed"] += 1
                    exit_code = 1
        except Exception as e:
            print(f"[AUDIO] Fout: {e}", file=sys.stderr)
            counter["failed"] += 1
            exit_code = 1

    # VIDEO
    if want_video:
        print(f"[*] Download VIDEO → {video_dir} ({len(urls)} bestanden)")
        v_opts = build_video_opts(video_dir, allow_playlists=args.allow_playlists)
        try:
            with YoutubeDL(v_opts) as ydl:
                ret = ydl.download(urls)
                if ret != 0:
                    counter["failed"] += 1
                    exit_code = 1
        except Exception as e:
            print(f"[VIDEO] Fout: {e}", file=sys.stderr)
            counter["failed"] += 1
            exit_code = 1

    # Summary
    success = counter["done"]
    failed = counter["failed"]
    print(f"\n✅ Klaar: {success} gelukt, ❌ {failed} mislukt.")
    write_log(f"Done: {success} ok, {failed} failed")

    if args.debug_threads:
        print_non_main_threads()

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    if args.hard_exit:
        os._exit(exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

