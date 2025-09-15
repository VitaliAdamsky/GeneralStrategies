import re
import logging
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not match:
        raise ValueError(f"Не удалось извлечь ID из ссылки: {url}")
    return match.group(1)

def fetch_transcript(video_url: str, language: str = "ru") -> list[dict]:
    video_id = extract_video_id(video_url)
    logging.info(f"Запрос транскрипта для видео: {video_url} (язык: {language})")

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=[language])
        logging.info("Транскрипт на русском найден.")
        return transcript

    except NoTranscriptFound:
        logging.warning("Транскрипт на русском не найден. Пробуем перевод.")
        try:
            transcript_list = ytt_api.list(video_id)
            original = transcript_list.find_transcript(['en', 'auto'])
            translated = original.translate(language)
            logging.info("Перевод выполнен.")
            return translated.fetch()
        except Exception as e:
            logging.error(f"Ошибка при переводе: {e}")
            raise

    except TranscriptsDisabled:
        logging.error("У видео отключены транскрипты.")
        raise

    except VideoUnavailable:
        logging.error("Видео недоступно.")
        raise

    except Exception as e:
        logging.error(f"Непредвиденная ошибка: {e}")
        raise

def save_transcript(video_url: str, transcript: list[dict]):
    video_id = extract_video_id(video_url)
    output_dir = Path("youtube_transcripts")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{video_id}.txt"

    # Заголовок видео — через YouTube HTML title
    import requests
    from bs4 import BeautifulSoup
    try:
        html = requests.get(video_url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title").text.replace(" - YouTube", "").strip()
    except Exception:
        title = "Без названия"

    header = f"Видео: {video_url}\nЗаголовок: {title}\n\n"
    body = "\n".join([entry["text"] for entry in transcript])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + body)

    logging.info(f"Транскрипт сохранён: {output_path}")

if __name__ == "__main__":
    url = "https://www.youtube.com/watch?v=GEIRJMZIgpk"  # замени на нужную ссылку
    try:
        transcript_data = fetch_transcript(url)
        save_transcript(url, transcript_data)
    except Exception as e:
        logging.error(f"Не удалось получить транскрипт: {e}")
