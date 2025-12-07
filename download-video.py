from yt_dlp import YoutubeDL

URL = "https://www.youtube.com/watch?v=e2jXTjUoJLo"
outtmpl = "/home/agguro/Videos/%(title)s.%(ext)s"

ydl_opts = {
    "outtmpl": outtmpl,
    "format": "mp4/bestvideo+bestaudio/best",
    "merge_output_format": "mp4",  # ffmpeg nodig om te muxen
}

with YoutubeDL(ydl_opts) as ydl:
    ydl.download([URL])

