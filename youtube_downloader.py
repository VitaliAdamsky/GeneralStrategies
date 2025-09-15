# 📦 Установка зависимостей
!pip install -q yt-dlp
!pip install -q git+https://github.com/openai/whisper.git
!pip install -q torch torchaudio tqdm --index-url https://download.pytorch.org/whl/cpu

# 📁 Импорт и подготовка
import os
import whisper
import yt_dlp
from tqdm import tqdm
from pathlib import Path
from google.colab import files
import re

# 🚀 Обработка массива ссылок
video_urls = [
    "https://www.youtube.com/watch?v=GEIRJMZIgpk",
    "https://www.youtube.com/watch?v=RN51gXUIR5k",
    "https://www.youtube.com/watch?v=ANOTHER_VIDEO_ID",
    # Добавь свои ссылки сюда
]

downloads_dir = Path("downloads")
transcripts_dir = Path("youtube_transcripts")
downloads_dir.mkdir(exist_ok=True)
transcripts_dir.mkdir(exist_ok=True)

# 📤 Загрузка cookies.txt
print("📤 Загрузите cookies.txt")
uploaded = files.upload()

cookies_path = None
for filename in uploaded:
    if "cookie" in filename.lower():
        cookies_path = filename
        break

if not cookies_path:
    raise RuntimeError("❌ cookies.txt не найден.")
else:
    print(f"✅ Cookies загружены: {cookies_path}")

# 📥 Скачивание аудио
def download_audio(video_url, cookies_path):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(downloads_dir / "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "cookiefile": cookies_path,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        audio_path = downloads_dir / f"{info['id']}.mp3"
        return audio_path, info["title"], info["id"]

# 🧠 Транскрипция
def transcribe_audio(audio_path, language="ru"):
    model = whisper.load_model("base")
    result = model.transcribe(str(audio_path), language=language, verbose=False)
    return result["text"]

# 📄 Сохранение транскрипта с уникальным именем
def sanitize(text):
    return re.sub(r"[^\w\-]", "_", text)[:50]

def save_transcript(video_url, title, video_id, transcript):
    safe_title = sanitize(title)
    output_path = transcripts_dir / f"{video_id}_{safe_title}.txt"
    header = f"Видео: {video_url}\nЗаголовок: {title}\n\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + transcript)

 

for url in tqdm(video_urls, desc="📦 Обработка видео", unit="видео"):
    try:
        print(f"\n🔗 {url}")
        audio_path, title, video_id = download_audio(url, cookies_path)
        transcript = transcribe_audio(audio_path, language="ru")
        save_transcript(url, title, video_id, transcript)
        print(f"✅ Сохранено: {video_id}_{sanitize(title)}.txt")
    except Exception as e:
        print(f"❌ Ошибка: {url}\n   Причина: {str(e)}")
