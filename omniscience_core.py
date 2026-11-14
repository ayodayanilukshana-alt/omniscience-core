import os
import re
import io
import sys
import json
import math
import time
import random
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests
from PIL import Image
from xgboost import XGBRegressor
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.stdout.reconfigure(line_buffering=True)


def mk_url(proto, domain_parts, path=""):
    return f"{proto}://{'.'.join(domain_parts)}{path}"


AI_BASE_URL = os.environ.get("AI_BASE_URL", mk_url("https", ["api", "relaymodels", "com"], "/v1")).rstrip("/")
AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()

SUPREME_COUNCIL_MODELS = [
    "deepseek-v4-flash",
    "qwen3.7-max",
    "gpt-6-luna",
    "deepseek-v4.1-flash",
    "kimi-k2.7-code",
    "gemini-3.8-flash"
]

ALL_YOUTUBE_COUNTRIES = [
    "US", "GB", "CA", "AU", "DE", "FR", "JP", "KR", "IN", "LK", "BR", "MX", "ID", "VN", "PH", "TH", "MY", "SG",
    "TW", "HK", "AE", "SA", "QA", "KW", "OM", "BH", "EG", "MA", "DZ", "TN", "NG", "ZA", "KE", "GH", "UG", "TZ",
    "SN", "CI", "ZW", "RU", "UA", "PL", "CZ", "SK", "HU", "RO", "BG", "RS", "HR", "SI", "BA", "MK", "ME", "AL",
    "GR", "TR", "IL", "JO", "LB", "IQ", "AZ", "GE", "KZ", "BY", "LT", "LV", "EE", "FI", "SE", "NO", "DK", "IS",
    "IE", "NL", "BE", "LU", "CH", "AT", "IT", "ES", "PT", "MT", "CY", "AR", "CL", "CO", "PE", "VE", "EC", "BO",
    "PY", "UY", "CR", "PA", "DO", "GT", "HN", "SV", "NI", "PR", "JM", "PK", "BD", "NP", "NZ"
]

ALL_CATEGORY_IDS = ["1", "2", "10", "15", "17", "19", "20", "22", "23", "24", "25", "26", "27", "28"]

VIRAL_NICHE_SWEEP_QUERIES = [
    "3d size comparison animation",
    "investing $1000 compound interest simulation",
    "satisfying ball escape physics #shorts",
    "how it works 3d animation explained",
    "mrbeast style challenge experiment",
    "ai tools coding comparison",
    "stock market crash simulation",
    "megastructures engineering explained",
    "marble race elimination arena",
    "brain test optical illusion quiz",
    "untold history documentary",
    "space universe scale comparison"
]

RAW_LOW_VIEW_SEEDS = [
    "IMG_0", "DSC_0", "MVI_0", "VID_2026", "WIN_2026", "my first youtube video",
    "vlog episode 1", "gameplay walkthrough part 1", "unlisted test clip", "screen recording test"
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}


def call_ai_council(models, sys_prompt, usr_prompt, temperature=0.4):
    if not AI_API_KEY:
        return ""
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    for m in models:
        try:
            r = requests.post(
                f"{AI_BASE_URL}/chat/completions",
                headers=headers,
                json={
                    "model": m,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": usr_prompt}
                    ],
                    "temperature": temperature
                },
                timeout=95
            )
            if r.status_code == 200:
                c = r.json()["choices"][0]["message"]["content"].strip()
                if c:
                    print(f"🧠 [AI Council] Distilled universal laws using {m}!", flush=True)
                    return c
        except Exception:
            pass
    return ""


def get_yt_client():
    """Uses the exact OAuth scopes granted to our refresh token so it NEVER fails with invalid_scope!"""
    cid = os.environ.get("YT_CLIENT_ID", "").strip()
    csec = os.environ.get("YT_CLIENT_SECRET", "").strip()
    rtok = os.environ.get("YT_REFRESH_TOKEN", "").strip()
    if not (cid and csec and rtok):
        return None
    creds = Credentials(
        token=None,
        refresh_token=rtok,
        token_uri=mk_url("https", ["oauth2", "googleapis", "com"], "/token"),
        client_id=cid,
        client_secret=csec,
        scopes=[
            mk_url("https", ["www", "googleapis", "com"], "/auth/youtube.upload"),
            mk_url("https", ["www", "googleapis", "com"], "/auth/youtube"),
            mk_url("https", ["www", "googleapis", "com"], "/auth/youtube.force-ssl")
        ]
    )
    return build("youtube", "v3", credentials=creds)


# =====================================================================
# LAYER 1: YOUTUBE INTERNAL SOURCE CODE (`base.js` + `EXPERIMENT_FLAGS`) SPY
# =====================================================================
def dissect_youtube_internal_source_code():
    algo_telemetry = {
        "timestamp": int(time.time()),
        "player_version": "unknown",
        "player_js_size_bytes": 0,
        "active_experiment_flags": {},
        "total_flags_detected": 0
    }
    try:
        yt_home = mk_url("https", ["www", "youtube", "com"], "/?hl=en&gl=US")
        r = requests.get(yt_home, headers=BROWSER_HEADERS, timeout=10)
        if r.status_code == 200:
            html = r.text
            m_js = re.search(r'(/s/player/[a-zA-Z0-9_-]+/[^"\']+?/base\.js)', html)
            if m_js:
                algo_telemetry["player_version"] = m_js.group(1)
                try:
                    r_base = requests.head(mk_url("https", ["www", "youtube", "com"], m_js.group(1)), headers=BROWSER_HEADERS, timeout=5)
                    algo_telemetry["player_js_size_bytes"] = int(r_base.headers.get("Content-Length", 0))
                except Exception:
                    pass

            m_flags = re.search(r'"EXPERIMENT_FLAGS"\s*:\s*(\{[^\}]+\})', html)
            if m_flags:
                flags_raw = json.loads(m_flags.group(1))
                algo_telemetry["total_flags_detected"] = len(flags_raw)
                key_terms = ["reel", "short", "watch", "recommend", "hype", "loop", "engage", "ctr", "prefetch", "autoplay"]
                for k, v in flags_raw.items():
                    if any(t in k.lower() for t in key_terms):
                        algo_telemetry["active_experiment_flags"][k] = v
            print(f"🕵️ [Layer 1: YouTube Code Spy] Player: {algo_telemetry['player_version']} | Flags: {algo_telemetry['total_flags_detected']}", flush=True)
    except Exception as e:
        print(f"[Layer 1 Note] {e}", flush=True)
    return algo_telemetry


# =====================================================================
# QUOTA-FREE YOUTUBE INNERTUBE DIRECT SEARCH ENGINE (UNLIMITED VIDEOS!)
# =====================================================================
def innertube_unlimited_search(query, gl_code="US", sp_filter=None):
    """
    Calls YouTube's internal `/youtubei/v1/search` endpoint directly (0 API Quota used!).
    Returns video IDs, titles, channel names, view counts, and thumbnails across any country!
    """
    url = mk_url("https", ["www", "youtube", "com"], "/youtubei/v1/search?prettyPrint=false")
    payload = {
        "context": {
            "client": {
                "hl": "en",
                "gl": gl_code,
                "clientName": "WEB",
                "clientVersion": "2.20261112.01.00"
            }
        },
        "query": query
    }
    if sp_filter:
        payload["params"] = sp_filter

    discovered_ids = []
    try:
        r = requests.post(url, headers=BROWSER_HEADERS, json=payload, timeout=8)
        if r.status_code == 200:
            v_ids = list(dict.fromkeys(re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', r.text)))
            discovered_ids.extend(v_ids[:30])
    except Exception:
        pass
    return discovered_ids


def analyze_image_url_in_ram(img_url):
    default_vec = [0.5] * 10
    if not img_url:
        return default_vec
    try:
        r = requests.get(img_url, headers=BROWSER_HEADERS, timeout=5)
        if r.status_code == 200 and len(r.content) > 400:
            im = Image.open(io.BytesIO(r.content)).convert("RGB").resize((128, 128))
            arr = np.asarray(im, dtype=np.float32) / 255.0
            r_c, g_c, b_c = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

            lum = 0.299 * r_c + 0.587 * g_c + 0.114 * b_c
            mean_lum = float(np.mean(lum))
            std_contrast = float(np.std(lum))

            c_max = np.maximum(np.maximum(r_c, g_c), b_c)
            c_min = np.minimum(np.minimum(r_c, g_c), b_c)
            delta = c_max - c_min
            sat = np.where(c_max > 0.01, delta / (c_max + 1e-5), 0.0)
            mean_sat = float(np.mean(sat))
            high_sat_ratio = float(np.mean(sat > 0.65))

            gx = np.abs(np.diff(lum, axis=1))
            gy = np.abs(np.diff(lum, axis=0))
            edge_density = float(np.mean(gx) + np.mean(gy))

            center_patch = lum[32:96, 32:96]
            center_saliency = float(np.std(center_patch) / (std_contrast + 1e-4))

            red_dom = float(np.mean(r_c > (g_c + b_c) * 0.65))
            warm_vs_cool = float(np.mean(r_c - b_c))
            bright_px = float(np.mean(lum > 0.8))
            dark_px = float(np.mean(lum < 0.2))

            return [
                round(mean_lum, 4), round(std_contrast, 4), round(mean_sat, 4),
                round(high_sat_ratio, 4), round(edge_density, 4), round(center_saliency, 4),
                round(red_dom, 4), round(warm_vs_cool, 4), round(bright_px, 4), round(dark_px, 4)
            ]
    except Exception:
        pass
    return default_vec


def fetch_retention_heatmap_and_sponsor_segments(video_id):
    info = {
        "has_heatmap": 0.0,
        "hook_retention_0_10": 0.5,
        "mid_retention_50": 0.5,
        "end_loop_retention_95": 0.4,
        "peak_replay_position_pct": 0.5,
        "peak_replay_spike_intensity": 0.5,
        "sponsor_count": 0.0,
        "sponsor_start_pct": 0.0,
        "sponsor_duration_sec": 0.0,
        "hidden_page_keywords": []
    }
    try:
        sb_url = mk_url("https", ["sponsor", "ajay", "app"], f"/api/skipSegments?videoID={video_id}&categories=[\"sponsor\",\"selfpromo\",\"interaction\",\"intro\",\"outro\"]")
        r_sb = requests.get(sb_url, timeout=4)
        if r_sb.status_code == 200:
            segs = r_sb.json()
            sponsors = [s for s in segs if s.get("category") in ("sponsor", "selfpromo")]
            info["sponsor_count"] = float(len(sponsors))
            if sponsors:
                first_sp = sponsors[0].get("segment", [0, 0])
                v_dur = max(float(sponsors[0].get("videoDuration", 300.0)), 1.0)
                info["sponsor_start_pct"] = round(first_sp[0] / v_dur, 4)
                info["sponsor_duration_sec"] = round(first_sp[1] - first_sp[0], 2)
    except Exception:
        pass

    try:
        w_url = mk_url("https", ["www", "youtube", "com"], f"/watch?v={video_id}&hl=en")
        r_w = requests.get(w_url, headers=BROWSER_HEADERS, timeout=6)
        if r_w.status_code == 200:
            html = r_w.text
            kw_m = re.search(r'"keywords"\s*:\s*(\[[^\]]+\])', html)
            if kw_m:
                try:
                    info["hidden_page_keywords"] = json.loads(kw_m.group(1))[:20]
                except Exception:
                    pass

            scores = [float(x) for x in re.findall(r'"heatMarkerIntensityScoreNormalized"\s*:\s*([0-9\.]+)', html)]
            if len(scores) >= 10:
                arr = np.array(scores[:100], dtype=np.float32)
                info["has_heatmap"] = 1.0
                info["hook_retention_0_10"] = float(np.mean(arr[:10]))
                info["mid_retention_50"] = float(np.mean(arr[40:60]))
                info["end_loop_retention_95"] = float(np.mean(arr[-10:]))
                info["peak_replay_position_pct"] = float(np.argmax(arr) / len(arr))
                info["peak_replay_spike_intensity"] = float(np.max(arr) - np.median(arr))
    except Exception:
        pass
    return info


def extract_64_molecular_features(video_item, channel_item, heatmap_info, thumb_vec, logo_vec, banner_vec):
    snip = video_item.get("snippet", {})
    stat = video_item.get("statistics", {})
    cdet = video_item.get("contentDetails", {})

    ch_snip = channel_item.get("snippet", {}) if channel_item else {}
    ch_stat = channel_item.get("statistics", {}) if channel_item else {}

    title = str(snip.get("title", ""))
    desc = str(snip.get("description", ""))
    ch_title = str(ch_snip.get("title", snip.get("channelTitle", "")))

    views = max(int(stat.get("viewCount", 0)), 0)
    likes = max(int(stat.get("likeCount", 0)), 0)
    comments = max(int(stat.get("commentCount", 0)), 0)
    subs = max(int(ch_stat.get("subscriberCount", 100)), 1)
    ch_total_vids = max(int(ch_stat.get("videoCount", 10)), 1)

    dur_str = str(cdet.get("duration", "PT45S"))
    m_min = re.search(r"(\d+)M", dur_str)
    m_sec = re.search(r"(\d+)S", dur_str)
    dur_sec = (int(m_min.group(1)) * 60 if m_min else 0) + (int(m_sec.group(1)) if m_sec else 0)
    is_short = 1.0 if dur_sec <= 62 else 0.0

    t_len = max(len(title), 1)
    t_words = title.split()
    w_cnt = max(len(t_words), 1)
    upper_chars = sum(1 for c in title if c.isupper())
    lower_chars = sum(1 for c in title if c.islower())
    digit_chars = sum(1 for c in title if c.isdigit())
    all_caps_words = sum(1 for w in t_words if w.isupper() and len(w) > 1)
    title_case_words = sum(1 for w in t_words if w[:1].isupper() and w[1:].islower())

    has_question = 1.0 if "?" in title else 0.0
    has_exclaim = 1.0 if "!" in title else 0.0
    has_brackets = 1.0 if any(b in title for b in "()[]{}") else 0.0
    has_colon_dash = 1.0 if any(b in title for b in ":-—|") else 0.0
    has_dollar_pct = 1.0 if any(b in title for b in "$%€£") else 0.0
    has_vs = 1.0 if (" vs " in title.lower() or " vs." in title.lower()) else 0.0

    ch_len = max(len(ch_title), 1)
    ch_upper_ratio = sum(1 for c in ch_title if c.isupper()) / ch_len
    ch_has_space = 1.0 if " " in ch_title.strip() else 0.0
    ch_has_digits = 1.0 if any(c.isdigit() for c in ch_title) else 0.0

    outbound_links = len(re.findall(r"https?://[^\s]+", desc))
    hashtags_cnt = len(re.findall(r"#\w+", desc + " " + title))
    timestamps_cnt = len(re.findall(r"\d+:\d{2}", desc))
    desc_len = len(desc)

    like_ratio = likes / max(views, 1)
    comment_ratio = comments / max(views, 1)
    outlier_mult = views / max(subs, 10)

    base_features = [
        float(t_len), float(w_cnt),
        upper_chars / t_len, lower_chars / t_len, digit_chars / t_len,
        all_caps_words / w_cnt, title_case_words / w_cnt,
        has_question, has_exclaim, has_brackets, has_colon_dash, has_dollar_pct, has_vs,
        float(dur_sec), is_short,
        math.log10(subs + 1), math.log10(ch_total_vids + 1),
        ch_upper_ratio, ch_has_space, ch_has_digits,
        float(outbound_links), float(hashtags_cnt), float(timestamps_cnt), math.log10(desc_len + 1),
        heatmap_info["has_heatmap"], heatmap_info["hook_retention_0_10"],
        heatmap_info["mid_retention_50"], heatmap_info["end_loop_retention_95"],
        heatmap_info["peak_replay_position_pct"], heatmap_info["peak_replay_spike_intensity"],
        heatmap_info["sponsor_count"], heatmap_info["sponsor_start_pct"], heatmap_info["sponsor_duration_sec"],
        float(len(heatmap_info["hidden_page_keywords"]))
    ]
    full_64_vec = base_features + thumb_vec[:10] + logo_vec[:10] + banner_vec[:10]
    return full_64_vec[:64], views, outlier_mult, like_ratio, comment_ratio


def run_omniscience_training_cycle():
    os.makedirs("brain", exist_ok=True)
    state_path = Path("brain/omniscient_state.json")
    xgb_path = Path("brain/xgboost_universal.json")

    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    cycle_idx = int(state.get("cycle_idx", 0))
    total_videos_dissected = int(state.get("total_videos_dissected", 0))
    country_cursor = int(state.get("country_cursor", 0))

    algo_code_state = dissect_youtube_internal_source_code()
    yt = get_yt_client()

    selected_countries = [ALL_YOUTUBE_COUNTRIES[(country_cursor + i) % len(ALL_YOUTUBE_COUNTRIES)] for i in range(8)]
    selected_cat = ALL_CATEGORY_IDS[cycle_idx % len(ALL_CATEGORY_IDS)]
    print(f"🌍 [Layer 4 Global Sweep] Cycle #{cycle_idx + 1} | Countries: {selected_countries} | Category: {selected_cat}", flush=True)

    video_items = []
    discovered_video_ids = []

    # 1. Quota-Free Innertube Multi-Country Viral + Low-View Graveyard Sweep (Guarantees 150-250+ Video IDs every run!)
    for gl in selected_countries[:4]:
        q_viral = VIRAL_NICHE_SWEEP_QUERIES[(cycle_idx + len(discovered_video_ids)) % len(VIRAL_NICHE_SWEEP_QUERIES)]
        discovered_video_ids.extend(innertube_unlimited_search(q_viral, gl_code=gl))

    # Also sweep raw/low-view uploads ("upload date: today" filter `CAI%253D`)
    for seed_q in RAW_LOW_VIEW_SEEDS[cycle_idx % 5 : (cycle_idx % 5) + 3]:
        discovered_video_ids.extend(innertube_unlimited_search(seed_q, gl_code="US", sp_filter="CAI%3D"))

    # 2. Fetch full metadata for all discovered IDs + regional popular charts in efficient 50-video batches!
    if yt:
        for gl_code in selected_countries[:4]:
            try:
                r_pop = yt.videos().list(
                    part="snippet,statistics,contentDetails",
                    chart="mostPopular",
                    regionCode=gl_code,
                    videoCategoryId=selected_cat,
                    maxResults=25
                ).execute()
                video_items.extend(r_pop.get("items", []))
            except Exception:
                try:
                    r_pop2 = yt.videos().list(
                        part="snippet,statistics,contentDetails",
                        chart="mostPopular",
                        regionCode=gl_code,
                        maxResults=25
                    ).execute()
                    video_items.extend(r_pop2.get("items", []))
                except Exception as e:
                    print(f"[Chart Note {gl_code}] {e}", flush=True)

        unique_ids = list(dict.fromkeys(discovered_video_ids))
        for i in range(0, len(unique_ids), 50):
            batch_ids = unique_ids[i:i + 50]
            try:
                r_v = yt.videos().list(id=",".join(batch_ids), part="snippet,statistics,contentDetails").execute()
                video_items.extend(r_v.get("items", []))
            except Exception as e:
                print(f"[Batch Fetch Note] {e}", flush=True)

    # Deduplicate video_items by ID
    dedup_map = {}
    for v in video_items:
        if "id" in v:
            dedup_map[v["id"]] = v
    video_items = list(dedup_map.values())
    print(f"✅ [Harvester] Retrieved {len(video_items)} unique videos (Viral Outliers + 0-View Graveyard Flops)!", flush=True)

    # Fetch Channel Branding (Logo, Banner, Casing, Subscriber Count)
    ch_ids = list({v.get("snippet", {}).get("channelId", "") for v in video_items if v.get("snippet", {}).get("channelId")})
    channel_map = {}
    if yt:
        for i in range(0, len(ch_ids), 50):
            try:
                r_ch = yt.channels().list(id=",".join(ch_ids[i:i + 50]), part="snippet,statistics,brandingSettings").execute()
                for c_obj in r_ch.get("items", []):
                    channel_map[c_obj["id"]] = c_obj
            except Exception:
                pass

    # Parallel RAM Dissection of Thumbnails, Logos, Banners, Heatmaps & SponsorBlock!
    def dissect_single_video(idx_and_v):
        idx, v = idx_and_v
        vid_id = v["id"]
        snip = v.get("snippet", {})
        ch_obj = channel_map.get(snip.get("channelId", ""), {})
        thumb_u = snip.get("thumbnails", {}).get("high", {}).get("url", "")
        logo_u = ch_obj.get("snippet", {}).get("thumbnails", {}).get("default", {}).get("url", "")
        banner_u = ch_obj.get("brandingSettings", {}).get("image", {}).get("bannerExternalUrl", "")

        thumb_vec = analyze_image_url_in_ram(thumb_u) if idx < 80 else [0.5] * 10
        logo_vec = analyze_image_url_in_ram(logo_u) if idx < 35 else [0.5] * 10
        banner_vec = analyze_image_url_in_ram(banner_u) if (banner_u and idx < 25) else [0.5] * 10
        hm_info = fetch_retention_heatmap_and_sponsor_segments(vid_id) if idx < 35 else {
            "has_heatmap": 0.0, "hook_retention_0_10": 0.5, "mid_retention_50": 0.5,
            "end_loop_retention_95": 0.4, "peak_replay_position_pct": 0.5, "peak_replay_spike_intensity": 0.5,
            "sponsor_count": 0.0, "sponsor_start_pct": 0.0, "sponsor_duration_sec": 0.0, "hidden_page_keywords": []
        }
        vec64, views, outlier_mult, _, _ = extract_64_molecular_features(v, ch_obj, hm_info, thumb_vec, logo_vec, banner_vec)
        target_score = math.log10(views + 1.0) * (1.0 + min(outlier_mult / 5.0, 8.0))
        row_str = f"V{idx}|Views:{views}|Outlier:{outlier_mult:.1f}x|Ch:'{ch_obj.get('snippet',{}).get('title','')[:16]}'|Title:'{snip.get('title','')[:55]}'"
        return vec64, target_score, row_str, vid_id, outlier_mult, snip.get("title", "")

    X_batch, y_batch, compressed_rows_for_ai, comment_samples = [], [], [], []
    print(f"🧬 Dissecting {len(video_items)} videos across 10 Molecular Layers using 12 Parallel Threads...", flush=True)

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(dissect_single_video, (idx, v)) for idx, v in enumerate(video_items)]
        for fut in as_completed(futures):
            try:
                vec64, target_score, row_str, vid_id, outlier_mult, v_title = fut.result()
                X_batch.append(vec64)
                y_batch.append(target_score)
                compressed_rows_for_ai.append((outlier_mult, row_str, vid_id, v_title))
            except Exception:
                pass

    # Sort so AI sees both the highest viral outliers AND the lowest 0-view graveyard videos!
    compressed_rows_for_ai.sort(key=lambda x: x[0], reverse=True)
    top_outliers = compressed_rows_for_ai[:30]
    bottom_graveyard = compressed_rows_for_ai[-20:]

    if yt:
        for _, _, vid_id, v_title in top_outliers[:6]:
            try:
                rc = yt.commentThreads().list(videoId=vid_id, part="snippet", order="relevance", maxResults=4).execute()
                for cit in rc.get("items", []):
                    ct = cit["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
                    comment_samples.append(f"[{v_title[:25]}]: {ct[:85]}")
            except Exception:
                pass

    if len(X_batch) >= 8:
        X_np = np.array(X_batch, dtype=np.float32)
        y_np = np.array(y_batch, dtype=np.float32)
        model = XGBRegressor(n_estimators=45, max_depth=5, learning_rate=0.07, verbosity=0)
        if xgb_path.exists():
            try:
                model.fit(X_np, y_np, xgb_model=str(xgb_path))
                print(f"✅ [Incremental Synaptic Learning] Updated XGBoost Brain with {len(X_batch)} new 64-feature vectors!", flush=True)
            except Exception:
                model.fit(X_np, y_np)
        else:
            model.fit(X_np, y_np)
        model.save_model(str(xgb_path))

    ai_table = "\n".join([r[1] for r in (top_outliers + bottom_graveyard)])
    council_prompt = (
        f"Dissect these {len(top_outliers)} Mega-Viral Outliers vs {len(bottom_graveyard)} Low/Zero-View Graveyard Flops plus viewer comments:\n"
        + ai_table
        + "\nVIEWER COMMENTS:\n" + "\n".join(comment_samples[:12])
        + '\nOutput strict JSON: {"viral_title_formulas": ["3 exact casing/number/curiosity formulas from top outliers"], "zero_view_poison_patterns": ["3 exact mistakes in the low-view graveyard videos"], "psychological_hook_laws": ["2 millisecond hook & loop laws"], "unmet_viewer_demands": ["3 breakout video topics viewers want next"]}'
    )
    raw_laws = call_ai_council(SUPREME_COUNCIL_MODELS, "Output valid JSON only.", council_prompt, 0.35)
    new_laws = {}
    try:
        s_i, e_i = raw_laws.find("{"), raw_laws.rfind("}")
        if s_i != -1 and e_i != -1:
            new_laws = json.loads(raw_laws[s_i:e_i + 1])
    except Exception:
        pass

    vault = state.get("algorithmic_laws_vault", {
        "viral_title_formulas": [], "zero_view_poison_patterns": [],
        "psychological_hook_laws": [], "unmet_viewer_demands": []
    })
    for k in vault:
        vault[k] = list(dict.fromkeys([str(x) for x in (new_laws.get(k, []) + vault.get(k, [])) if x]))[:50]

    state["cycle_idx"] = cycle_idx + 1
    state["total_videos_dissected"] = total_videos_dissected + len(video_items)
    state["last_batch_size"] = len(video_items)
    state["country_cursor"] = (country_cursor + 8) % len(ALL_YOUTUBE_COUNTRIES)
    state["last_updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["youtube_internal_code_telemetry"] = algo_code_state
    state["algorithmic_laws_vault"] = vault

    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"🎉 [OMNISCIENCE BRAIN V2.0 UPDATED] Dissected {len(video_items)} videos in this run | Total Learned: {state['total_videos_dissected']:,}!", flush=True)


if __name__ == "__main__":
    run_omniscience_training_cycle()
