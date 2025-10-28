#!/usr/bin/env python3
# flickr_to_miro_grouped_v2_coerced.py
import os
import sys
import time
import requests

# ==== CONFIG (env vars or hardcode here) ====
FLICKR_API_KEY    = os.getenv("FLICKR_API_KEY")         # Flickr API key
FLICKR_USER_ID    = os.getenv("FLICKR_USER_ID")         # Owner NSID, e.g. "12345678@N00"
FLICKR_PHOTOSETID = os.getenv("FLICKR_PHOTOSET_ID")     # Album (photoset) ID
MIRO_TOKEN        = os.getenv("MIRO_TOKEN")             # Miro OAuth token (needs boards:write)
MIRO_BOARD_ID     = os.getenv("MIRO_BOARD_ID")          # Target board ID

# Layout (absolute positions; no parent container)
IMAGES_PER_ROW    = int(os.getenv("IMAGES_PER_ROW", "6"))
CELL_W            = float(os.getenv("CELL_W", "440"))   # tile width (image width target)
CELL_H            = float(os.getenv("CELL_H", "420"))   # tile height (image + banner)
START_X           = float(os.getenv("START_X", "0"))
START_Y           = float(os.getenv("START_Y", "0"))

# Overlay banner (light bg so default black text is readable)
OVERLAY_HEIGHT    = float(os.getenv("OVERLAY_HEIGHT", "60"))
OVERLAY_MARGIN    = float(os.getenv("OVERLAY_MARGIN", "8"))    # gap below image
OVERLAY_COLOR     = os.getenv("OVERLAY_COLOR", "#FFFFFF")
TEXT_SIZE         = int(os.getenv("TEXT_SIZE", "18"))
TEXT_PADDING_X    = float(os.getenv("TEXT_PADDING_X", "8"))

# Progress bar
PROGRESS_WIDTH    = int(os.getenv("PROGRESS_WIDTH", "40"))

FLICKR_ENDPOINT = "https://www.flickr.com/services/rest/"
MIRO_BASE       = "https://api.miro.com/v2"

session = requests.Session()
if MIRO_TOKEN:
    session.headers.update({"Authorization": f"Bearer {MIRO_TOKEN}"})


# ---------- Flickr helpers ----------

def flickr_photos_in_photoset(photoset_id, user_id, api_key):
    """Yield photos from a Flickr album (with direct URL extras)."""
    page = 1
    while True:
        params = {
            "method": "flickr.photosets.getPhotos",
            "api_key": api_key,
            "user_id": user_id,
            "photoset_id": photoset_id,
            "extras": "media,path_alias,original_format,url_o,url_k,url_h,url_l,url_c,url_z,url_m",
            "per_page": 500,
            "page": page,
            "format": "json",
            "nojsoncallback": 1
        }
        r = requests.get(FLICKR_ENDPOINT, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        photoset = data.get("photoset")
        if not photoset or "photo" not in photoset:
            break
        for p in photoset["photo"]:
            yield p
        if page >= int(photoset.get("pages", 1)):
            break
        page += 1


def pick_best_image_url(p):
    """Prefer slightly-larger-than-medium sizes; skip videos."""
    if p.get("media") == "video":
        return None
    for key in ("url_c", "url_l", "url_z", "url_m", "url_h", "url_k", "url_o"):
        if key in p:
            return p[key]
    return None


def build_flickr_page_url(p, fallback_user_id):
    """Compute the photo page URL."""
    user = p.get("path_alias") or fallback_user_id
    return f"https://www.flickr.com/photos/{user}/{p['id']}"


# ---------- Miro helpers ----------

def _miro_post(url, payload, tries=2):
    """POST with simple 429 retry; prints error body on failure."""
    for attempt in range(tries):
        r = session.post(url, json=payload, timeout=60)
        if r.status_code == 429 and attempt + 1 < tries:
            time.sleep(2)
            continue
        try:
            r.raise_for_status()
        except requests.HTTPError:
            print("   Miro error body:", r.text[:400])
            raise
        return r.json()
    raise RuntimeError("Failed after retries")


def miro_create_image(board_id, image_url, x, y, width=None, height=None):
    """Create an image by URL (no base64)."""
    endpoint = f"{MIRO_BASE}/boards/{board_id}/images"
    payload = {
        "data": {"url": image_url},
        "position": {"x": x, "y": y}
    }
    if width or height:
        payload["geometry"] = {}
        if width is not None:
            payload["geometry"]["width"] = width
        if height is not None:
            payload["geometry"]["height"] = height
    return _miro_post(endpoint, payload)


def miro_create_shape_rect(board_id, x, y, width, height, fill="#FFFFFF"):
    """Create a filled rectangle (overlay banner)."""
    endpoint = f"{MIRO_BASE}/boards/{board_id}/shapes"
    payload = {
        "data": {"shape": "rectangle"},
        "position": {"x": x, "y": y},
        "geometry": {"width": width, "height": height},
        "style": {"fillColor": fill}
    }
    return _miro_post(endpoint, payload)


def miro_create_text(board_id, content, x, y, width=380, font_size=18, align="center"):
    """Create a text item (URLs auto-linkify in Miro)."""
    endpoint = f"{MIRO_BASE}/boards/{board_id}/texts"
    payload = {
        "data": {"content": content},    # required (rich/plain text)
        "position": {"x": x, "y": y},
        "geometry": {"width": width},
        "style": {
            "textAlign": align,
            "fontSize": font_size
            # NOTE: textColor isn't supported by v2; use light overlays instead
        }
    }
    return _miro_post(endpoint, payload)


def _coerce_ids_to_numbers(ids_list):
    """Coerce string IDs like '12345' to ints where possible (leave others as-is)."""
    out = []
    for _id in ids_list:
        if isinstance(_id, str) and _id.isdigit():
            out.append(int(_id))
        else:
            out.append(_id)
    return out


def miro_group_items(board_id, item_ids):
    """
    Group items so they move together.
    Tries multiple payload shapes to handle schema variations:
      1) {"data":{"items":[<number>, ...]}}
      2) {"data":{"itemIds":[<id>, ...]}}
      3) {"itemIds":[<id>, ...]}
    Raises if all fail (caller will warn and continue).
    """
    endpoint = f"{MIRO_BASE}/boards/{board_id}/groups"

    ids_numbers = _coerce_ids_to_numbers(item_ids)
    payloads = [
        {"data": {"items": ids_numbers}},
        {"data": {"itemIds": item_ids}},
        {"itemIds": item_ids},
    ]

    last_err = None
    for p in payloads:
        try:
            return _miro_post(endpoint, p)
        except requests.HTTPError as e:
            last_err = e
            try:
                print("   Miro error body:", e.response.text[:400])
            except Exception:
                pass
            continue

    raise last_err


# ---------- Progress helpers ----------

def progress_bar(i, n, width=40):
    ratio = 0 if n == 0 else i / n
    filled = int(ratio * width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {i}/{n}"


def print_progress(i, n, suffix=""):
    bar = progress_bar(i, n, PROGRESS_WIDTH)
    end = "\n" if i == n else "\r"
    sys.stdout.write(f"{bar} {suffix}{end}")
    sys.stdout.flush()


# ---------- Main ----------

def main():
    missing = [k for k, v in {
        "FLICKR_API_KEY": FLICKR_API_KEY,
        "FLICKR_USER_ID": FLICKR_USER_ID,
        "FLICKR_PHOTOSET_ID": FLICKR_PHOTOSETID,
        "MIRO_TOKEN": MIRO_TOKEN,
        "MIRO_BOARD_ID": MIRO_BOARD_ID,
    }.items() if not v]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")

    photos = list(flickr_photos_in_photoset(FLICKR_PHOTOSETID, FLICKR_USER_ID, FLICKR_API_KEY))
    total = len(photos)
    if total == 0:
        print("No photos found (album may be private or IDs incorrect).")
        return

    print(f"Found {total} photos. Uploading to Miro board {MIRO_BOARD_ID}…")

    done = 0
    for idx, p in enumerate(photos, start=1):
        pid = p.get("id")
        title = (p.get("title") or "").strip()
        img_url = pick_best_image_url(p)

        if not img_url:
            print_progress(idx, total, suffix=f"skip {pid} (no usable image URL or video)")
            continue

        # Absolute tile placement (no parent container constraints)
        col = (idx - 1) % IMAGES_PER_ROW
        row = (idx - 1) // IMAGES_PER_ROW
        x_center = START_X + col * CELL_W
        y_center = START_Y + row * CELL_H

        created_ids = []

        # 1) Image (nudge up a bit to make room for banner)
        try:
            img = miro_create_image(
                MIRO_BOARD_ID,
                img_url,
                x=x_center,
                y=y_center - OVERLAY_HEIGHT/2 - OVERLAY_MARGIN/2,
                width=CELL_W - 24
            )
            iid = img.get("id")
            if iid is not None:
                created_ids.append(iid)
        except requests.HTTPError as e:
            print_progress(idx, total, suffix=f"ERR {pid} (image) -> {e}")
            continue

        # 2) Overlay banner rectangle (below image)
        overlay_y = y_center + (CELL_H / 2) - (OVERLAY_HEIGHT / 2) - 4
        try:
            rect = miro_create_shape_rect(
                MIRO_BOARD_ID,
                x_center,
                overlay_y,
                width=(CELL_W - 24),
                height=OVERLAY_HEIGHT,
                fill=OVERLAY_COLOR
            )
            rid = rect.get("id")
            if rid is not None:
                created_ids.append(rid)
        except requests.HTTPError as e:
            print_progress(idx, total, suffix=f"ERR {pid} (overlay) -> {e}")

        # 3) Text label (auto-linkified URL) on the banner
        flickr_page = build_flickr_page_url(p, FLICKR_USER_ID)
        label_text = f"{title} — {flickr_page}" if title else flickr_page
        try:
            text = miro_create_text(
                MIRO_BOARD_ID,
                label_text,
                x=x_center,
                y=overlay_y,
                width=(CELL_W - 24 - 2*TEXT_PADDING_X),
                font_size=TEXT_SIZE,
                align="center"
            )
            tid = text.get("id")
            if tid is not None:
                created_ids.append(tid)
        except requests.HTTPError as e:
            print_progress(idx, total, suffix=f"ERR {pid} (text) -> {e}")

        # 4) Group them so they move together
        group_ids = [i for i in created_ids if i is not None]
        if len(group_ids) >= 2:
            try:
                _ = miro_group_items(MIRO_BOARD_ID, group_ids)
            except requests.HTTPError as e:
                print_progress(idx, total, suffix=f"warn {pid} (group) -> {e}")

        done += 1
        print_progress(idx, total, suffix=f"ok {pid}")
        time.sleep(0.12)  # gentle pacing

    print(f"Done. Placed {done}/{total} grouped tiles.")


if __name__ == "__main__":
    main()
