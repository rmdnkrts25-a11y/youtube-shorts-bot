import os
import json
import random
import subprocess
import urllib.parse
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Ortam değişkenlerinden (GitHub Secrets) anahtarları al
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
PIXABAY_API_KEY = (
    os.environ.get("PIXABAY_API_KEY", "").strip()
    or os.environ.get("PEXELS_API_KEY", "").strip()
)
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

USED_TOPICS_FILE = "used_topics.txt"


def load_used_topics():
    if not os.path.exists(USED_TOPICS_FILE):
        return []
    with open(USED_TOPICS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def save_used_topic(topic):
    with open(USED_TOPICS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{topic}\n")


def generate_script_with_gemini(used_topics):
    print("1/5 - Gemini API ile benzersiz İngilizce Shorts senaryosu üretiliyor...")
    used_str = ", ".join(used_topics[-80:]) if used_topics else "None"

    prompt = f"""
You are an expert viral YouTube Shorts scriptwriter for a high-retention channel about dark psychology, stoic paradoxes, cognitive biases, and fascinating historical mysteries.

Previously covered topics (DO NOT repeat any of these): {used_str}

Pick ONE brand new, mind-blowing psychological effect, philosophical paradox, or historical mystery.
Create a gripping YouTube Short in English that lasts around 40-50 seconds (approx. 95 to 115 words).

Rules for 'narration':
- Must start with an irresistible hook in the first sentence.
- Plain spoken English text ONLY. No asterisks, no emojis, no stage directions like [Pause], no hashtags inside narration.
- End with a seamless loop or thought-provoking twist that makes viewers comment.

Rules for 'search_terms':
- Provide exactly 3 simple 2-word visual search queries for stock video search (e.g., "dark ocean", "ancient statue", "storm clouds").

Return ONLY valid JSON with this exact structure:
{{
  "topic_name": "Name of the Paradox or Effect",
  "title": "Viral Title Under 60 Characters #shorts",
  "description": "Engaging 2-sentence description explaining the concept.\\n\\n#psychology #stoicism #mindset #facts #shorts",
  "narration": "Full spoken English voiceover text here...",
  "search_terms": ["query one", "query two", "query three"]
}}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.85
        }
    }

    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    result = json.loads(raw_text)

    if "#shorts" not in result["title"].lower():
        result["title"] = f"{result['title'][:85]} #shorts"

    print(f"Secilen Konu: {result['topic_name']}")
    print(f"Baslik: {result['title']}")
    return result


def generate_voiceover_and_subtitles(narration_text):
    print("2/5 - Doğal İngilizce seslendirme ve senkronize altyazı üretiliyor...")
    voices = [
        "en-US-ChristopherNeural",
        "en-US-EricNeural",
        "en-US-GuyNeural"
    ]
    chosen_voice = random.choice(voices)

    cmd = [
        "edge-tts",
        "--voice", chosen_voice,
        "--rate=+6%",
        "--text", narration_text,
        "--write-media", "voice.mp3",
        "--write-subtitles", "subs.vtt"
    ]
    subprocess.run(cmd, check=True)

    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        "voice.mp3"
    ]
    out = subprocess.check_output(probe_cmd).decode("utf-8").strip()
    duration = float(out)
    print(f"Seslendirme tamamlandı ({duration:.1f} saniye).")
    return duration


def fetch_pixabay_clip(query, filename):
    """Pixabay Video API üzerinden curl kullanarak stok video indirir."""
    if not PIXABAY_API_KEY:
        return False

    encoded_q = urllib.parse.quote(query)
    api_url = (
        f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}"
        f"&q={encoded_q}&per_page=15&safesearch=true"
    )
    try:
        out = subprocess.check_output(
            ["curl", "-s", "-L", "-A", "Mozilla/5.0", api_url],
            timeout=25
        ).decode("utf-8", errors="ignore")
        data = json.loads(out)
        hits = data.get("hits", [])
        if not hits:
            return False

        random.shuffle(hits)
        for hit in hits:
            videos = hit.get("videos", {})
            for quality in ["large", "medium", "small"]:
                v_info = videos.get(quality, {})
                v_url = v_info.get("url")
                if v_url:
                    subprocess.run(
                        ["curl", "-s", "-L", "-A", "Mozilla/5.0", "-o", filename, v_url],
                        check=True,
                        timeout=60
                    )
                    if os.path.exists(filename) and os.path.getsize(filename) > 50000:
                        return True
    except Exception as e:
        print(f"Pixabay arama uyarısı ({query}): {e}")
    return False


def generate_ai_cinematic_clip(query, filename, duration=16.0):
    """Anahtarsız Yedek Motor: AI sinematik dikey görsel üretip hareketli kamerayla videoya çevirir."""
    prompt_str = f"dark moody cinematic vertical photography of {query}, dramatic lighting, stoic philosophical atmosphere, 8k, no text"
    encoded_prompt = urllib.parse.quote(prompt_str)
    seed = random.randint(1000, 999999)
    img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={seed}"
    img_file = f"temp_{seed}.jpg"

    try:
        subprocess.run(
            ["curl", "-s", "-L", "-A", "Mozilla/5.0", "-o", img_file, img_url],
            check=True,
            timeout=45
        )
        if os.path.exists(img_file) and os.path.getsize(img_file) > 10000:
            vf = (
                "scale=1220:2168:force_original_aspect_ratio=increase,"
                "crop=1080:1920:'(iw-ow)/2':'((ih-oh)/2)+((ih-oh)/3)*sin(t/2.5)',"
                "eq=brightness=-0.12:contrast=1.15,fps=30,format=yuv420p"
            )
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", img_file,
                "-t", f"{duration:.2f}", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-an", filename
            ], check=True)
            return True
    except Exception as e:
        print(f"AI görsel yedek uyarısı: {e}")

    # Son çare çevrimdışı sinematik koyu arka plan
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x12161f:s=1080x1920:r=30:d={duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        filename
    ], check=True)
    return True


def download_background_videos(search_terms, total_duration):
    print("3/5 - Arka plan videoları hazırlanıyor (Pixabay API + AI Görsel Motoru)...")
    fallback_terms = ["dark ocean", "storm clouds", "night city", "forest fog", "stars night"]
    downloaded_files = []
    segment_duration = (total_duration / 3.0) + 1.0

    for idx, term in enumerate(search_terms[:3]):
        filename = f"raw_clip_{idx}.mp4"
        success = False

        # Önce Pixabay API ile dene
        for q in [term, random.choice(fallback_terms)]:
            if fetch_pixabay_clip(q, filename):
                print(f"Klip {idx + 1}/3 Pixabay üzerinden indirildi ({q}).")
                success = True
                break

        # Pixabay anahtarı yoksa veya sonuç çıkmadıysa AI Sinematik Sahne üret
        if not success:
            print(f"Klip {idx + 1}/3 için AI Sinematik Hareketli Sahne üretiliyor ({term})...")
            generate_ai_cinematic_clip(term, filename, segment_duration)

        downloaded_files.append(filename)

    return downloaded_files


def assemble_final_video(clip_files, total_duration):
    print("4/5 - FFmpeg ile 1080x1920 dikey montaj ve altyazı gömme işlemi yapılıyor...")
    segment_duration = (total_duration / len(clip_files)) + 0.4
    processed_clips = []

    for idx, clip in enumerate(clip_files):
        out_clip = f"norm_clip_{idx}.mp4"
        vf_filter = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "eq=brightness=-0.14:contrast=1.12,"
            "fps=30,format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", clip,
            "-t", f"{segment_duration:.2f}",
            "-vf", vf_filter,
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            out_clip
        ]
        subprocess.run(cmd, check=True)
        processed_clips.append(out_clip)

    with open("concat_list.txt", "w", encoding="utf-8") as f:
        for p_clip in processed_clips:
            f.write(f"file '{p_clip}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "concat_list.txt", "-c", "copy", "merged_bg.mp4"
    ], check=True)

    sub_style = (
        "subtitles=subs.vtt:force_style='"
        "Alignment=10,Fontname=DejaVu Sans,Fontsize=16,Bold=1,"
        "PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=1,MarginL=25,MarginR=25'"
    )

    final_cmd = [
        "ffmpeg", "-y",
        "-i", "merged_bg.mp4",
        "-i", "voice.mp3",
        "-vf", sub_style,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "final_short.mp4"
    ]
    subprocess.run(final_cmd, check=True)
    print("Montaj tamamlandı: final_short.mp4 hazır.")


def upload_to_youtube(video_path, title, description):
    print("5/5 - Video YouTube kanalına otomatik olarak yükleniyor...")
    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:95],
            "description": description,
            "tags": ["psychology", "stoicism", "facts", "paradox", "mindset", "shorts"],
            "categoryId": "27",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response.get("id")
    print(f"BAŞARILI! Video yayında: https://www.youtube.com/shorts/{video_id}")
    return video_id


def main():
    required_keys = [
        GEMINI_API_KEY,
        YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
    ]
    if not all(required_keys):
        raise ValueError("Eksik API anahtarı! Lütfen GEMINI_API_KEY ve YouTube anahtarlarını kontrol edin.")

    used_topics = load_used_topics()
    content = generate_script_with_gemini(used_topics)
    duration = generate_voiceover_and_subtitles(content["narration"])
    clips = download_background_videos(content["search_terms"], duration)
    assemble_final_video(clips, duration)
    upload_to_youtube("final_short.mp4", content["title"], content["description"])
    save_used_topic(content["topic_name"])


if __name__ == "__main__":
    main()
