from yt_dlp import YoutubeDL

URL = "https://www.youtube.com/watch?v=e2jXTjUoJLo"
outtmpl = "/home/agguro/Music/%(title)s.%(ext)s"

ydl_opts = {
    "outtmpl": outtmpl,
    "format": "bestaudio/best",   # kies beste audio
    "postprocessors": [
        {  # converteer naar mp3
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "192",  # kbps
        }
    ],
}

with YoutubeDL(ydl_opts) as ydl:
    ydl.download([URL])

