import os
import re
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
            "temperature": 0.85,
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
            text = text.replace("**", "").replace("##", "").replace("#", "").strip()
            if len(text.split()) >= 150:
                return text
        except Exception as e:
            last_err = e
            print(f"Metin üretim uyarısı (Deneme {attempt + 1}/3): {e}")
            time.sleep(2)
    raise last_err if last_err else ValueError("Bölüm metni üretilemedi.")


def generate_short_script(used_topics):
    print("1/6 - [SHORTS MODU] 27 sn yüksek tempolu + Seamless Loop senaryosu üretiliyor...")
    used_str = ", ".join(used_topics[-90:]) if used_topics else "None"

    prompt = f"""
You are an elite viral YouTube Shorts scriptwriter for 'Mind Paradox Daily' (dark psychology, stoic paradoxes, cognitive traps).

Previously covered topics (DO NOT repeat): {used_str}

Pick ONE brand new, mind-bending psychological effect or paradox (such as stubbornness loops, overthinking traps, silent manipulation, cognitive dissonance).
Write an ultra-tight, punchy 26-to-29-second YouTube Short script in English (STRICTLY 65 to 78 words total).

CRITICAL RETENTION RULES FOR 'narration':
1. RAZOR-SHARP 3-SECOND HOOK: Start immediately with a shocking question or provocative claim. ZERO greetings, ZERO channel intros, ZERO slow setup.
2. HIGH-PACING & ZERO FLUFF: Every single sentence must deliver a psychological revelation. Keep sentences crisp and rhythmic.
3. SEAMLESS LOOP ENDING: The final clause MUST grammatically and seamlessly flow directly into the very first word of the script so viewers loop the video without noticing!
   Example of seamless loop:
   - First sentence: "You unconsciously trust people who mirror your exact posture."
   - Last sentence: "...and that is the dark psychological reason why"
4. Plain spoken English text ONLY. No asterisks, no emojis, no stage directions.

Rules for 'search_terms':
- Provide exactly 8 distinct 2-word dark/cinematic visual search queries (so scenes cut every ~3.2 seconds for maximum retention).

Return ONLY valid JSON:
{{
  "topic_name": "Name of the Effect",
  "title": "Curiosity Gap Title Under 55 Characters #shorts",
  "description": "2-sentence punchy explanation of the psychological trap.\\n\\nQuestion for you: Have you ever noticed this pattern in your own life? Share your thoughts below.\\n\\n#psychology #stoicism #darkpsychology #mindset #shorts",
  "narration": "Full spoken English voiceover text (65-78 words)...",
  "search_terms": ["query 1", "query 2", "query 3", "query 4", "query 5", "query 6", "query 7", "query 8"]
}}
"""
    res = call_gemini_json(prompt, max_tokens=8192)
    if "#shorts" not in res["title"].lower():
        res["title"] = f"{res['title'][:85]} #shorts"
    return res


def generate_long_documentary_script(used_topics):
    print("1/6 - [11 DK BELGESEL MODU] Duygu odaklı başlık, yüksek CTR kapak ve 5 bölüm planlanıyor...")
    used_str = ", ".join(used_topics[-90:]) if used_topics else "None"
    recent_shorts_hint = ", ".join(used_topics[-5:]) if used_topics else "overthinking, stubborn mind loops, quiet dissatisfaction"

    outline_prompt = f"""
You are the lead documentary producer for 'Mind Paradox Daily', a prestigious psychology and philosophy YouTube channel (similar to Aperture, Pursuit of Wonder, and Einzelgänger).

Previously used long documentary topics (DO NOT repeat): {used_str}
Recent channel themes (great for deep-dive companion videos): {recent_shorts_hint}

Select ONE deep, relatable human psychological struggle (such as chronic dissatisfaction, stubbornness loops, fear of stillness, emotional exhaustion, self-sabotage, or silent social traps) for an 11-minute documentary.

CRITICAL CTR & RETENTION RULES:
1. EMOTION-DRIVEN TITLE (NO JARGON): Do NOT put academic/technical terms in the title! Focus directly on the raw human emotion, quiet pain, or everyday frustration the viewer feels (e.g., "Why Nothing You Achieve Ever Feels Like Enough", "Why Your Mind Refuses to Let Go of What Hurts You"). Under 62 characters.
2. HIGH-CONTRAST THUMBNAIL HOOK: 'thumbnail_text' MUST be 1 to 2 MASSIVE, ultra-readable words (MAX 13 characters, e.g., "NEVER ENOUGH", "MIND TRAP", "LET IT GO", "WAKE UP").
3. CHAPTER TITLES: Make the 5 chapter titles intriguing and relatable so viewers click timestamps.

Return ONLY valid JSON with this exact structure:
{{
  "topic_name": "Core Psychological Struggle",
  "title": "Emotion-Driven Relatable Title Under 62 Characters",
  "thumbnail_text": "1-2 WORDS MAX",
  "description_intro": "Compelling 3-sentence YouTube SEO description focused on the viewer's life transformation.",
  "discussion_question": "A thought-provoking question asking viewers to share their personal experience in the comments.",
  "chapters": [
    {{"title": "The Quiet Trap You Feel Every Day", "focus": "FIRST 60 SECONDS HOOK: Skip textbook definitions! Open with a deeply relatable emotional scene and make a crystal-clear promise of what will change in the viewer's life by watching until the end."}},
    {{"title": "Why Your Brain Keeps Repeating This Loop", "focus": "Detail real historical experiments, philosophers, or thinkers who uncovered why the human mind gets stuck here."}},
    {{"title": "The Hidden Cost Nobody Talks About", "focus": "Explain the deep neuroscience and hidden psychological triggers quietly draining their energy and peace."}},
    {{"title": "How Modern Life Feeds Your Restlessness", "focus": "Real-world examples in relationships, status games, phones, and daily habits."}},
    {{"title": "How to Permanently Break Free", "focus": "Actionable stoic & psychological mental models to rewire this habit, ending with a profound closing thought and a gentle invitation to subscribe for deeper clarity."}}
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
    chapter_word_counts = []

    for idx, ch in enumerate(blueprint["chapters"]):
        print(f"   -> Bölüm {idx + 1}/5 yazılıyor: {ch['title']} (~350 kelime)...")
        intro_rule = ""
        if idx == 0:
            intro_rule = (
                "CRITICAL FIRST-60-SECONDS RULE: Do NOT start with dry academic definitions or history! "
                "Start immediately with a vivid, intimate second-person ('you') emotional experience the viewer recognizes instantly, "
                "and explicitly promise how watching this video to the end will permanently change how they handle this feeling."
            )

        part_prompt = f"""
You are narrating Part {idx + 1} of 5 of an 11-minute YouTube documentary titled "{blueprint['title']}".

Current Chapter: {ch['title']}
Chapter Goal: {ch['focus']}
{intro_rule}

Write between 330 and 370 words of captivating, hypnotic spoken English narration for this section.
Strict Rules:
- Output ONLY the spoken paragraphs. Do NOT include any titles, headers, labels, bullet points, or "Part 1".
- Flow seamlessly as part of one continuous essay.
- Plain spoken English text ONLY. No asterisks, no markdown, no [Pause] tags.
- Use rich storytelling, concrete psychological examples, and deeply relatable insights.
"""
        section_text = call_gemini_text(part_prompt, max_tokens=8192)
        full_narration_parts.append(section_text)
        chapter_word_counts.append(len(section_text.split()))

    blueprint["narration"] = " ".join(full_narration_parts)
    blueprint["chapter_word_counts"] = chapter_word_counts
    total_words = sum(chapter_word_counts)
    print(f"Belgesel senaryosu tamamlandı: Toplam {total_words} kelime (~11 dakika).")
    return blueprint


def format_timestamp(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def build_long_description_with_timestamps(blueprint, total_duration):
    """5 bölümün gerçek kelime oranlarına göre milimetrik YouTube zaman damgaları ve etkileşim sorusu oluşturur."""
    intro = blueprint.get("description_intro", "").strip()
    question = blueprint.get(
        "discussion_question",
        "Which part of this video resonated with your current life the most? Let us know in the comments."
    ).strip()
    chapters = blueprint.get("chapters", [])
    word_counts = blueprint.get("chapter_word_counts", [])
    total_words = sum(word_counts) or 1

    lines = [
        intro,
        "",
        f"💬 Reflection Question: {question}",
        "",
        "Chapters:"
    ]
    elapsed = 0.0
    for idx, ch in enumerate(chapters):
        ts = "00:00" if idx == 0 else format_timestamp(elapsed)
        lines.append(f"{ts} {ch['title']}")
        if idx < len(word_counts):
            elapsed += total_duration * (word_counts[idx] / total_words)

    lines.append("")
    lines.append("Subscribe to Mind Paradox Daily for deep psychological & stoic documentaries every week.")
    lines.append("#psychology #stoicism #philosophy #documentary #mindset #selfimprovement")
    return "\n".join(lines)


def _vtt_time_to_seconds(t_str):
    parts = t_str.strip().replace(",", ".").split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return 0.0


def _seconds_to_ass_time(sec):
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_dynamic_shorts_ass(vtt_path="subs.vtt", ass_path="dynamic_subs.ass"):
    """VTT altyazısını 2-3 kelimelik hızlı, büyük ve anahtar kelimeleri sarı vurgulayan ASS formatına çevirir."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralShorts,DejaVu Sans,76,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,6,3,5,60,60,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    if not os.path.exists(vtt_path):
        return False

    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[\.,]\d{3}|\d{1,2}:\d{2}[\.,]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[\.,]\d{3}|\d{1,2}:\d{2}[\.,]\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)",
        re.DOTALL
    )

    events = []
    for match in pattern.finditer(content):
        start_s = _vtt_time_to_seconds(match.group(1))
        end_s = _vtt_time_to_seconds(match.group(2))
        raw_txt = re.sub(r"<[^>]+>", "", match.group(3)).replace("\n", " ").strip()
        words = [w for w in raw_txt.split() if w]
        if not words or end_s <= start_s:
            continue

        chunks = []
        i = 0
        while i < len(words):
            step = 2 if (len(words) - i) != 3 else 3
            chunks.append(words[i:i + step])
            i += step

        total_chars = sum(len("".join(c)) for c in chunks) or 1
        curr_t = start_s

        for idx, chunk in enumerate(chunks):
            chunk_chars = len("".join(chunk)) or 1
            dur = (end_s - start_s) * (chunk_chars / total_chars)
            next_t = end_s if idx == len(chunks) - 1 else min(end_s, curr_t + dur)

            upper_words = [w.upper() for w in chunk]
            longest_idx = max(range(len(upper_words)), key=lambda k: len(re.sub(r"\W", "", upper_words[k])))
            formatted_words = []
            for w_i, uw in enumerate(upper_words):
                safe_w = uw.replace("{", "").replace("}", "")
                if w_i == longest_idx and len(safe_w) >= 3:
                    formatted_words.append(r"{\c&H0000FFFF&}" + safe_w + r"{\c&H00FFFFFF&}")
                else:
                    formatted_words.append(safe_w)

            line_text = " ".join(formatted_words)
            events.append(
                f"Dialogue: 0,{_seconds_to_ass_time(curr_t)},{_seconds_to_ass_time(next_t)},ViralShorts,,0,0,0,,{line_text}"
            )
            curr_t = next_t

    if not events:
        return False

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return True


def generate_voiceover_and_ambient_audio(narration_text, is_long=False):
    print("2/6 - Doğal İngilizce seslendirme + Sinematik Dark Ambient arka plan müziği miksleniyor...")
    # Tekdüze yapay içerik (Repetitious content) algısını önlemek için doğal belgesel sesleri rotasyonu
    voices = [
        "en-US-ChristopherNeural",
        "en-US-EricNeural",
        "en-US-GuyNeural",
        "en-US-RogerNeural"
    ]
    chosen_voice = random.choice(voices)
    rate = "+0%" if is_long else "+8%"

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

    # Her videoda benzersiz akustik parmak izi için hafif frekans varyasyonu
    base_f = random.choice([108, 110, 112, 115])
    fade_out_d = 4.0 if is_long else 0.8
    fade_out_st = max(0.0, duration - fade_out_d)
    ambient_filter = (
        f"aevalsrc='0.12*sin(2*PI*{base_f}*t)+0.08*sin(2*PI*164.81*t)+0.06*sin(2*PI*{base_f*2}*t)+0.03*sin(2*PI*{base_f/2}*t)':s=44100:d={duration:.2f},"
        f"lowpass=f=280,afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_st:.2f}:d={fade_out_d:.2f}[bg];"
        "[0:a]volume=1.18[vo];"
        "[vo][bg]amix=inputs=2:duration=first:dropout_transition=2"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-i", "raw_voice.mp3",
        "-filter_complex", ambient_filter,
        "-c:a", "aac", "-b:a", "192k",
        "voice.m4a"
    ], check=True)

    print(f"Ses ({chosen_voice}) + Atmosferik Müzik Miksajı tamamlandı ({duration / 60:.1f} dakika / {duration:.1f} sn).")
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
                f"crop={w}:{h}:'((iw-ow)/2)+((iw-ow)/3)*sin(t/3.2)':'((ih-oh)/2)+((ih-oh)/3)*cos(t/3.2)',"
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
    target_count = 20 if is_long else 8
    print(f"3/6 - {target_count} adet sinematik sahne indiriliyor/üretiliyor...")
    fallback_terms = [
        "dark ocean", "storm clouds", "night city", "forest fog", "stars night",
        "ancient ruins", "candle flame", "clock gears", "chess board", "old library"
    ]
    terms = list(search_terms[:target_count])
    while len(terms) < target_count:
        terms.append(random.choice(fallback_terms))

    downloaded_files = []
    segment_duration = (total_duration / float(target_count)) + 0.6

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
    print(f"4/6 - FFmpeg ile {w}x{h} sinematik renk düzenlemesi, hızlı geçişler ve dinamik altyazı montajlanıyor...")
    segment_duration = (total_duration / len(clip_files)) + 0.25
    processed_clips = []

    for idx, clip in enumerate(clip_files):
        out_clip = f"norm_clip_{idx}.mp4"
        fade_d = 0.4 if is_long else 0.15
        fade_out_st = max(0.1, segment_duration - fade_d)
        vf_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            "eq=brightness=-0.12:contrast=1.18:saturation=0.88,"
            "vignette=PI/5,"
            f"fade=t=in:st=0:d={fade_d:.2f},fade=t=out:st={fade_out_st:.2f}:d={fade_d:.2f},"
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
        sub_filter = (
            "subtitles=subs.vtt:force_style='"
            "Alignment=2,Fontname=DejaVu Sans,Fontsize=18,Bold=1,"
            "PrimaryColour=&H00E6F5FF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=2,Shadow=1,MarginV=38'"
        )
    else:
        if build_dynamic_shorts_ass("subs.vtt", "dynamic_subs.ass"):
            sub_filter = "ass=dynamic_subs.ass"
        else:
            sub_filter = (
                "subtitles=subs.vtt:force_style='"
                "Alignment=10,Fontname=DejaVu Sans,Fontsize=18,Bold=1,"
                "PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=3,Shadow=1,MarginL=25,MarginR=25'"
            )

    output_name = "final_output.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-i", "merged_bg.mp4",
        "-i", "voice.m4a",
        "-vf", sub_filter,
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
    print("5/6 - 11 Dakikalık video için yüksek zıtlıklı, sade ve dev yazılı Kapak Fotoğrafı (Thumbnail) üretiliyor...")
    prompt_str = (
        f"minimalist high-contrast youtube thumbnail artwork about {topic_name}, "
        "single glowing golden silhouette standing in pitch black obsidian void, dramatic rim lighting, "
        "stark color contrast, clean negative space, cinematic 8k, absolutely no text"
    )
    encoded = urllib.parse.quote(prompt_str)
    seed = random.randint(1000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&seed={seed}"
    raw_thumb = "raw_thumb.jpg"
    final_thumb = "thumbnail.jpg"

    try:
        subprocess.run(["curl", "-s", "-L", "-A", "Mozilla/5.0", "-o", raw_thumb, url], check=True, timeout=45)
        if os.path.exists(raw_thumb) and os.path.getsize(raw_thumb) > 10000:
            words = ["".join(c for c in w.upper() if c.isalnum()) for w in hook_text.split()]
            words = [w for w in words if w][:2]
            clean_text = " ".join(words)[:14] if words else "WAKE UP"

            vf = (
                "scale=1280:720,eq=brightness=-0.12:contrast=1.32:saturation=1.15,"
                f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='{clean_text}':"
                "fontcolor=#FFD700:fontsize=104:borderw=8:bordercolor=black:x=(w-text_w)/2:y=h-155"
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
        final_description = build_long_description_with_timestamps(content, duration)
        thumb_path = generate_custom_thumbnail(
            content["topic_name"],
            content.get("thumbnail_text", content["topic_name"])
        )
    else:
        final_description = content.get("description", "")

    upload_to_youtube(final_video, content["title"], final_description, is_long=is_long, thumbnail_path=thumb_path)
    save_used_topic(content["topic_name"])


if __name__ == "__main__":
    main()
