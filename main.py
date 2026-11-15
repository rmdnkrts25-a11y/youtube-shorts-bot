import os
import json
import time
import random
import subprocess
import urllib.parse
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Ortam değişkenleri (GitHub Secrets)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
PIXABAY_API_KEY = (
    os.environ.get("PIXABAY_API_KEY", "").strip()
    or os.environ.get("PEXELS_API_KEY", "").strip()
)
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

# Çalışma modu: "short" (Her gün) veya "long" (2 günde bir 11 dk belgesel)
VIDEO_MODE = os.environ.get("VIDEO_MODE", "short").strip().lower()
USED_TOPICS_FILE = "used_topics.txt"


def load_used_topics():
    if not os.path.exists(USED_TOPICS_FILE):
        return []
    with open(USED_TOPICS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def save_used_topic(topic):
    with open(USED_TOPICS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{topic}\n")


def get_working_gemini_model():
    preferred_models = [
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.0-flash"
    ]
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
        res = requests.get(list_url, timeout=20)
        if res.status_code == 200:
            models = res.json().get("models", [])
            available = [
                m["name"].replace("models/", "")
                for m in models
                if "generateContent" in m.get("supportedGenerationMethods", [])
                and "flash" in m["name"].lower()
            ]
            for pref in preferred_models:
                if pref in available:
                    return pref
            if available:
                return available[0]
    except Exception as e:
        print(f"Model listesi uyarısı: {e}")
    return "gemini-3-flash-preview"


def call_gemini_json(prompt, max_tokens=8192):
    """JSON çıktısını yüksek token limiti ve otomatik yeniden deneme ile güvenli şekilde alır."""
    model_name = get_working_gemini_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.8,
            "maxOutputTokens": max_tokens
        }
    }

    last_err = None
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3].strip()
            return json.loads(raw_text)
        except Exception as e:
            last_err = e
            print(f"JSON yanıt uyarısı (Deneme {attempt + 1}/3): {e}")
            time.sleep(2)
    raise last_err


def call_gemini_text(prompt, max_tokens=8192):
    """Uzun belgesel bölümlerini JSON kısıtlaması olmadan kesintisiz saf metin olarak alır."""
    model_name = get_working_gemini_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.82,
            "maxOutputTokens": max_tokens
        }
    }

    last_err = None
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Olası markdown işaretlerini temizle
            text = text.replace("**", "").replace("##", "").replace("#", "").strip()
            if len(text.split()) >= 150:
                return text
        except Exception as e:
            last_err = e
            print(f"Metin üretim uyarısı (Deneme {attempt + 1}/3): {e}")
            time.sleep(2)
    raise last_err if last_err else ValueError("Bölüm metni üretilemedi.")


def generate_short_script(used_topics):
    print("1/6 - [SHORTS MODU] Gemini ile yüksek tutma oranlı Shorts senaryosu üretiliyor...")
    used_str = ", ".join(used_topics[-90:]) if used_topics else "None"

    prompt = f"""
You are a viral YouTube Shorts scriptwriter for 'Mind Paradox Daily', a channel about dark psychology, stoic paradoxes, cognitive biases, and historical mind traps.

Previously covered topics (DO NOT repeat): {used_str}

Pick ONE brand new, fascinating psychological effect or philosophical paradox.
Write a fast-paced 45-second YouTube Short script in English (105 to 125 words).

Rules for 'narration':
- Start with a shocking 1-sentence hook that stops scrolling immediately.
- Plain spoken English text ONLY. No asterisks, no emojis, no stage directions.
- End with an open loop question that triggers comments.

Rules for 'search_terms':
- Provide exactly 5 distinct 2-word visual search queries for stock video clips.

Return ONLY valid JSON:
{{
  "topic_name": "Name of the Effect",
  "title": "Curiosity Gap Title Under 58 Characters #shorts",
  "description": "2-sentence explanation of the paradox.\\n\\n#psychology #stoicism #darkpsychology #mindset #shorts",
  "narration": "Full spoken English voiceover text...",
  "search_terms": ["query 1", "query 2", "query 3", "query 4", "query 5"]
}}
"""
    res = call_gemini_json(prompt, max_tokens=8192)
    if "#shorts" not in res["title"].lower():
        res["title"] = f"{res['title'][:85]} #shorts"
    return res


def generate_long_documentary_script(used_topics):
    print("1/6 - [11 DK BELGESEL MODU] Ana konu, 5 bölüm planı ve 20 görsel sahne kurgulanıyor...")
    used_str = ", ".join(used_topics[-90:]) if used_topics else "None"

    outline_prompt = f"""
You are the lead documentary producer for 'Mind Paradox Daily', a prestigious psychology and philosophy YouTube channel (similar to Aperture, Pursuit of Wonder, and Einzelgänger).

Previously covered topics (DO NOT repeat): {used_str}

Select ONE deep, mesmerizing psychological phenomenon, stoic paradox, or dark human behavior mystery for an 11-minute documentary.

Create a 5-Act Documentary Blueprint and 20 visual scene queries.
Return ONLY valid JSON with this exact structure:
{{
  "topic_name": "Name of the Phenomenon",
  "title": "Intriguing Documentary Title Under 65 Characters",
  "thumbnail_text": "3-4 WORD SHOCKING HOOK",
  "description": "Compelling 3-sentence YouTube SEO description.\\n\\n00:00 The Hidden Trap\\n02:15 Historical Origins\\n04:30 The Psychological Mechanism\\n06:45 Modern Manipulation\\n09:00 The Stoic Antidote\\n\\n#psychology #stoicism #philosophy #documentary #mindset",
  "chapters": [
    {{"act": "Act 1: The Hook & The Unseen Paradox", "focus": "Start with a vivid storytelling scenario and introduce the core mystery."}},
    {{"act": "Act 2: The Famous Experiment & Historical Roots", "focus": "Detail real historical experiments, philosophers, or thinkers who uncovered this."}},
    {{"act": "Act 3: Inside the Brain's Blind Spot", "focus": "Explain the deep neuroscience and hidden psychological triggers behind why humans fall for it."}},
    {{"act": "Act 4: How Modern Society Weaponizes This", "focus": "Real-world examples in relationships, status games, media, and daily life."}},
    {{"act": "Act 5: The Stoic & Psychological Antidote", "focus": "Actionable mental models to break free and a profound philosophical closing thought."}}
  ],
  "search_terms": [
    "dark ocean", "ancient statue", "chess board", "storm clouds", "crowd walking",
    "old library", "burning candle", "hourglass sand", "night city", "mirror reflection",
    "forest fog", "clock gears", "greek temple", "rain window", "stars galaxy",
    "shadow hallway", "writing fountain", "mountain peak", "eye closeup", "calm waves"
  ]
}}
"""
    blueprint = call_gemini_json(outline_prompt, max_tokens=8192)
    print(f"Belgesel Konusu: {blueprint['topic_name']} | Başlık: {blueprint['title']}")

    full_narration_parts = []
    for idx, ch in enumerate(blueprint["chapters"]):
        print(f"   -> Bölüm {idx + 1}/5 yazılıyor: {ch['act']} (~350 kelime)...")
        part_prompt = f"""
You are narrating Part {idx + 1} of 5 of an 11-minute YouTube documentary titled "{blueprint['title']}" about "{blueprint['topic_name']}".

Current Section: {ch['act']}
Section Goal: {ch['focus']}

Write between 330 and 370 words of captivating, hypnotic spoken English narration for this section.
Strict Rules:
- Output ONLY the spoken paragraphs. Do NOT include any titles, headers, labels, bullet points, or "Part 1".
- Flow seamlessly as part of one continuous essay.
- Plain spoken English text ONLY. No asterisks, no markdown, no [Pause] tags.
- Use rich storytelling, concrete psychological examples, and thought-provoking insights.
"""
        section_text = call_gemini_text(part_prompt, max_tokens=8192)
        full_narration_parts.append(section_text)

    blueprint["narration"] = " ".join(full_narration_parts)
    total_words = len(blueprint["narration"].split())
    print(f"Belgesel senaryosu tamamlandı: Toplam {total_words} kelime (~11 dakika).")
    return blueprint


def generate_voiceover_and_ambient_audio(narration_text, is_long=False):
    print("2/6 - Doğal İngilizce seslendirme + Sinematik Dark Ambient arka plan müziği miksleniyor...")
    chosen_voice = "en-US-ChristopherNeural"
    rate = "+0%" if is_long else "+5%"

    subprocess.run([
        "edge-tts",
        "--voice", chosen_voice,
        "--rate=" + rate,
        "--text", narration_text,
        "--write-media", "raw_voice.mp3",
        "--write-subtitles", "subs.vtt"
    ], check=True)

    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        "raw_voice.mp3"
    ]
    duration = float(subprocess.check_output(probe_cmd).decode("utf-8").strip())

    ambient_filter = (
        f"aevalsrc='0.12*sin(2*PI*110*t)+0.08*sin(2*PI*164.81*t)+0.06*sin(2*PI*220*t)+0.03*sin(2*PI*55*t)':s=44100:d={duration:.2f},"
        "lowpass=f=280,afade=t=in:st=0:d=3,afade=t=out:st=" + f"{max(0, duration - 4):.2f}:d=4[bg];"
        "[0:a]volume=1.15[vo];"
        "[vo][bg]amix=inputs=2:duration=first:dropout_transition=2"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-i", "raw_voice.mp3",
        "-filter_complex", ambient_filter,
        "-c:a", "aac", "-b:a", "192k",
        "voice.m4a"
    ], check=True)

    print(f"Ses + Atmosferik Müzik Miksajı tamamlandı ({duration / 60:.1f} dakika / {duration:.0f} sn).")
    return duration


def fetch_pixabay_clip(query, filename):
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


def generate_ai_cinematic_clip(query, filename, duration, is_long=False):
    w, h = (1920, 1080) if is_long else (1080, 1920)
    scale_w, scale_h = (2112, 1188) if is_long else (1220, 2168)

    prompt_str = f"dark moody cinematic photography of {query}, chiaroscuro lighting, stoic philosophical atmosphere, 8k masterpiece, no text"
    encoded_prompt = urllib.parse.quote(prompt_str)
    seed = random.randint(1000, 999999)
    img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={w}&height={h}&nologo=true&seed={seed}"
    img_file = f"temp_{seed}.jpg"

    try:
        subprocess.run(
            ["curl", "-s", "-L", "-A", "Mozilla/5.0", "-o", img_file, img_url],
            check=True,
            timeout=45
        )
        if os.path.exists(img_file) and os.path.getsize(img_file) > 10000:
            vf = (
                f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:'((iw-ow)/2)+((iw-ow)/3)*sin(t/4.0)':'((ih-oh)/2)+((ih-oh)/3)*cos(t/4.0)',"
                "eq=brightness=-0.12:contrast=1.18:saturation=0.85,fps=30,format=yuv420p"
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

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x10141d:s={w}x{h}:r=30:d={duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        filename
    ], check=True)
    return True


def download_background_videos(search_terms, total_duration, is_long=False):
    target_count = 20 if is_long else 5
    print(f"3/6 - {target_count} adet sinematik sahne indiriliyor/üretiliyor...")
    fallback_terms = [
        "dark ocean", "storm clouds", "night city", "forest fog", "stars night",
        "ancient ruins", "candle flame", "clock gears", "chess board", "old library"
    ]
    terms = list(search_terms[:target_count])
    while len(terms) < target_count:
        terms.append(random.choice(fallback_terms))

    downloaded_files = []
    segment_duration = (total_duration / float(target_count)) + 0.8

    for idx, term in enumerate(terms):
        filename = f"raw_clip_{idx}.mp4"
        success = False

        if idx % 3 != 2:
            for q in [term, random.choice(fallback_terms)]:
                if fetch_pixabay_clip(q, filename):
                    print(f"Sahne {idx + 1}/{target_count} Pixabay HD stok video indirildi ({q}).")
                    success = True
                    break

        if not success:
            print(f"Sahne {idx + 1}/{target_count} Konuya Özel AI Sinematik Sahne üretiliyor ({term})...")
            generate_ai_cinematic_clip(term, filename, segment_duration, is_long=is_long)

        downloaded_files.append(filename)

    return downloaded_files


def assemble_final_video(clip_files, total_duration, is_long=False):
    w, h = (1920, 1080) if is_long else (1080, 1920)
    print(f"4/6 - FFmpeg ile {w}x{h} sinematik renk düzenlemesi, geçişler ve altyazı montajlanıyor...")
    segment_duration = (total_duration / len(clip_files)) + 0.35
    processed_clips = []

    for idx, clip in enumerate(clip_files):
        out_clip = f"norm_clip_{idx}.mp4"
        fade_out_st = max(0.1, segment_duration - 0.45)
        vf_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            "eq=brightness=-0.12:contrast=1.16:saturation=0.88,"
            "vignette=PI/5,"
            f"fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out_st:.2f}:d=0.4,"
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

    if is_long:
        sub_style = (
            "subtitles=subs.vtt:force_style='"
            "Alignment=2,Fontname=DejaVu Sans,Fontsize=18,Bold=1,"
            "PrimaryColour=&H00E6F5FF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=2,Shadow=1,MarginV=38'"
        )
    else:
        sub_style = (
            "subtitles=subs.vtt:force_style='"
            "Alignment=10,Fontname=DejaVu Sans,Fontsize=16,Bold=1,"
            "PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=2,Shadow=1,MarginL=25,MarginR=25'"
        )

    output_name = "final_output.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-i", "merged_bg.mp4",
        "-i", "voice.m4a",
        "-vf", sub_style,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "copy",
        "-shortest",
        output_name
    ], check=True)
    print(f"Montaj tamamlandı: {output_name}")
    return output_name


def generate_custom_thumbnail(topic_name, hook_text):
    print("5/6 - 11 Dakikalık video için yüksek tıklanma oranlı Kapak Fotoğrafı (Thumbnail) üretiliyor...")
    prompt_str = (
        f"dark dramatic youtube thumbnail artwork representing {topic_name}, "
        "ancient stoic marble statue with glowing golden cracks, mysterious cinematic lighting, ultra detailed, 8k"
    )
    encoded = urllib.parse.quote(prompt_str)
    seed = random.randint(1000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&seed={seed}"
    raw_thumb = "raw_thumb.jpg"
    final_thumb = "thumbnail.jpg"

    try:
        subprocess.run(["curl", "-s", "-L", "-A", "Mozilla/5.0", "-o", raw_thumb, url], check=True, timeout=45)
        if os.path.exists(raw_thumb) and os.path.getsize(raw_thumb) > 10000:
            clean_text = "".join(c for c in hook_text.upper() if c.isalnum() or c == " ")[:28]
            vf = (
                "scale=1280:720,eq=brightness=-0.10:contrast=1.25,"
                f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='{clean_text}':"
                "fontcolor=yellow:fontsize=64:borderw=5:bordercolor=black:x=(w-text_w)/2:y=h-120"
            )
            subprocess.run(["ffmpeg", "-y", "-i", raw_thumb, "-vf", vf, final_thumb], check=True)
            if os.path.exists(final_thumb):
                return final_thumb
    except Exception as e:
        print(f"Thumbnail üretim uyarısı: {e}")
    return None


def upload_to_youtube(video_path, title, description, is_long=False, thumbnail_path=None):
    print("6/6 - Video YouTube kanalına yükleniyor...")
    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    tags = ["psychology", "stoicism", "philosophy", "dark psychology", "mindset", "human behavior"]
    if not is_long:
        tags.append("shorts")

    body = {
        "snippet": {
            "title": title[:95],
            "description": description,
            "tags": tags,
            "categoryId": "27",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=5 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Yükleme ilerlemesi: %{int(status.progress() * 100)}")

    video_id = response.get("id")
    print(f"BAŞARILI! Video yayında: https://www.youtube.com/watch?v={video_id}")

    if is_long and thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
            ).execute()
            print("Özel Kapak Fotoğrafı (Thumbnail) başarıyla eklendi!")
        except Exception as e:
            print(f"Thumbnail yükleme bilgisi: {e}")

    return video_id


def main():
    required_keys = [
        GEMINI_API_KEY,
        YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
    ]
    if not all(required_keys):
        raise ValueError("Eksik API anahtarı! Lütfen GitHub Secrets ayarlarını kontrol edin.")

    is_long = (VIDEO_MODE == "long")
    used_topics = load_used_topics()

    if is_long:
        content = generate_long_documentary_script(used_topics)
    else:
        content = generate_short_script(used_topics)

    duration = generate_voiceover_and_ambient_audio(content["narration"], is_long=is_long)
    clips = download_background_videos(content["search_terms"], duration, is_long=is_long)
    final_video = assemble_final_video(clips, duration, is_long=is_long)

    thumb_path = None
    if is_long:
        thumb_path = generate_custom_thumbnail(
            content["topic_name"],
            content.get("thumbnail_text", content["topic_name"])
        )

    upload_to_youtube(final_video, content["title"], content["description"], is_long=is_long, thumbnail_path=thumb_path)
    save_used_topic(content["topic_name"])


if __name__ == "__main__":
    main()
