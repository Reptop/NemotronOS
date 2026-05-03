from __future__ import annotations

import random
import time
from urllib.parse import quote_plus, urlparse
from typing import Any

from .desktop_base import DesktopBackend

try:
    from PIL import Image, ImageStat
except ImportError:  # pragma: no cover - Pillow is a project dependency at runtime
    Image = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]


SITE_ALIASES = {
    "canvas": "https://canvas.oregonstate.edu/",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
}

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}

YOUTUBE_RANDOM_TOPICS = (
    "interesting science video",
    "tiny desk concert",
    "coding project demo",
    "space documentary short",
    "art restoration video",
    "3blue1brown",
    "computer history documentary",
    "relaxing jazz live session",
)

YOUTUBE_RECOMMENDED_CLICK_POINTS = (
    (0.23, 0.38),
    (0.47, 0.38),
    (0.71, 0.38),
    (0.23, 0.63),
    (0.47, 0.63),
    (0.71, 0.63),
)

YOUTUBE_THUMBNAIL_ASPECT_RATIO = 16 / 9


def app_launch(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    app_name = str(arguments.get("app_name", "")).strip()
    if not app_name:
        raise ValueError("app_launch requires app_name.")

    return desktop_backend.launch_app(app_name)


def keyboard_type(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    text = str(arguments.get("text", ""))
    if not text:
        raise ValueError("keyboard_type requires text.")

    return desktop_backend.type_text(text)


def mouse_click(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    if "x_ratio" in arguments or "y_ratio" in arguments:
        x_ratio = _ratio(arguments.get("x_ratio"), "x_ratio")
        y_ratio = _ratio(arguments.get("y_ratio"), "y_ratio")
        return desktop_backend.click_foreground_relative(x_ratio, y_ratio)

    try:
        x = int(arguments["x"])
        y = int(arguments["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("mouse_click requires x/y or x_ratio/y_ratio.") from exc

    return desktop_backend.click_at(x, y)


def browser_open(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    raw_target = str(arguments.get("url") or arguments.get("target") or "").strip()
    if not raw_target:
        raise ValueError("browser_open requires url.")

    url = normalize_browser_target(raw_target)
    return desktop_backend.open_browser(url)


def youtube_open(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    action = str(arguments.get("action") or "home").strip().lower()
    query = str(arguments.get("query") or "").strip()
    video_url = str(arguments.get("video_url") or arguments.get("url") or "").strip()
    video_id = str(arguments.get("video_id") or "").strip()

    url, resolved_action, resolved_query = build_youtube_url(
        action=action,
        query=query,
        video_url=video_url,
        video_id=video_id,
    )
    result = desktop_backend.open_browser(url)
    return {
        **result,
        "site": "youtube",
        "action": resolved_action,
        **({"query": resolved_query} if resolved_query else {}),
    }


def youtube_click_video(
    arguments: dict[str, Any],
    desktop_backend: DesktopBackend,
) -> dict[str, Any]:
    selection = str(arguments.get("selection") or "first_result").strip().lower()
    wait_seconds = float(arguments.get("wait_seconds", 2.5))
    if wait_seconds > 0:
        time.sleep(min(wait_seconds, 10.0))

    focus_result = desktop_backend.focus_window("youtube")
    if focus_result.get("focused"):
        time.sleep(0.35)

    screenshot_result = _click_youtube_thumbnail_from_screenshot(
        selection,
        desktop_backend,
        focus_result,
    )
    if screenshot_result is not None:
        return screenshot_result

    if selection in {"first_result", "first", "search_result"}:
        x_ratio, y_ratio = (0.34, 0.34)
        heuristic = "first YouTube search result"
    elif selection in {"random_visible", "recommended", "random_recommended"}:
        x_ratio, y_ratio = random.choice(YOUTUBE_RECOMMENDED_CLICK_POINTS)
        heuristic = "random visible YouTube recommendation grid point"
    else:
        raise ValueError(
            "youtube_click_video selection must be first_result or random_visible."
        )

    result = desktop_backend.click_foreground_relative(x_ratio, y_ratio)
    return {
        **result,
        "site": "youtube",
        "selection": selection,
        "click_strategy": "foreground_ratio_fallback",
        "focus_result": focus_result,
        "heuristic": heuristic,
    }


def _click_youtube_thumbnail_from_screenshot(
    selection: str,
    desktop_backend: DesktopBackend,
    focus_result: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        screenshot = desktop_backend.capture_screen()
    except Exception:  # noqa: BLE001 - clicking can fall back without screenshot support
        return None

    image_path = screenshot.get("path") or screenshot.get("image_ref")
    if not image_path or not isinstance(image_path, str) or image_path.startswith("mock://"):
        return None

    candidates = find_youtube_thumbnail_candidates(
        image_path=image_path,
        foreground_window=screenshot.get("foreground_window"),
        virtual_screen_origin=screenshot.get("virtual_screen_origin"),
    )
    target = choose_youtube_thumbnail_candidate(selection, candidates)
    if not target:
        return None

    result = desktop_backend.click_at(target["center_x"], target["center_y"])
    return {
        **result,
        "site": "youtube",
        "selection": selection,
        "click_strategy": "screenshot_thumbnail_detection",
        "focus_result": focus_result,
        "screenshot": image_path,
        "candidate_count": len(candidates),
        "target": target,
    }


def choose_youtube_thumbnail_candidate(
    selection: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None

    max_score = max(float(candidate.get("score", 0.0)) for candidate in candidates)
    strong_candidates = [
        candidate
        for candidate in candidates
        if float(candidate.get("score", 0.0)) >= max(35.0, max_score * 0.80)
    ]
    sorted_candidates = sorted(strong_candidates or candidates, key=lambda item: (item["top"], item["left"]))
    if selection in {"first_result", "first", "search_result"}:
        return sorted_candidates[0]
    if selection in {"random_visible", "recommended", "random_recommended"}:
        pool = sorted_candidates[: min(9, len(sorted_candidates))]
        return random.choice(pool)
    raise ValueError("youtube_click_video selection must be first_result or random_visible.")


def find_youtube_thumbnail_candidates(
    image_path: str,
    foreground_window: dict[str, Any] | None = None,
    virtual_screen_origin: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if Image is None or ImageStat is None:
        return []

    with Image.open(image_path) as image:
        rgb_image = image.convert("RGB")
        image_width, image_height = rgb_image.size

        origin_x = _int_or_default(
            (virtual_screen_origin or {}).get("x"),
            0,
        )
        origin_y = _int_or_default(
            (virtual_screen_origin or {}).get("y"),
            0,
        )
        search_bounds = _thumbnail_search_bounds(
            image_width,
            image_height,
            foreground_window,
            origin_x,
            origin_y,
        )

        candidates = _scan_thumbnail_candidates(
            rgb_image,
            search_bounds,
            origin_x,
            origin_y,
            image_width,
            image_height,
        )
        return _dedupe_thumbnail_candidates(candidates)


def _thumbnail_search_bounds(
    image_width: int,
    image_height: int,
    foreground_window: dict[str, Any] | None,
    origin_x: int,
    origin_y: int,
) -> tuple[int, int, int, int]:
    if foreground_window:
        left = _int_or_default(foreground_window.get("left"), origin_x) - origin_x
        top = _int_or_default(foreground_window.get("top"), origin_y) - origin_y
        right = _int_or_default(foreground_window.get("right"), origin_x + image_width) - origin_x
        bottom = _int_or_default(foreground_window.get("bottom"), origin_y + image_height) - origin_y
    else:
        left, top, right, bottom = 0, 0, image_width, image_height

    left = max(0, min(left, image_width - 1))
    top = max(0, min(top, image_height - 1))
    right = max(left + 1, min(right, image_width))
    bottom = max(top + 1, min(bottom, image_height))

    width = right - left
    height = bottom - top
    content_left = left + round(width * 0.07)
    content_top = top + round(height * 0.16)
    content_right = right - round(width * 0.03)
    content_bottom = bottom - round(height * 0.04)
    return content_left, content_top, content_right, content_bottom


def _scan_thumbnail_candidates(
    image: Any,
    bounds: tuple[int, int, int, int],
    origin_x: int,
    origin_y: int,
    image_width: int,
    image_height: int,
) -> list[dict[str, Any]]:
    left, top, right, bottom = bounds
    width = right - left
    if width < 160 or bottom - top < 120:
        return []

    thumbnail_widths = sorted(
        {
            max(180, min(520, round(width * 0.22))),
            max(220, min(620, round(width * 0.30))),
            max(260, min(720, round(width * 0.38))),
        }
    )
    candidates: list[dict[str, Any]] = []
    for thumb_width in thumbnail_widths:
        thumb_height = round(thumb_width / YOUTUBE_THUMBNAIL_ASPECT_RATIO)
        if thumb_height < 90 or thumb_width >= width or thumb_height >= bottom - top:
            continue

        x_step = max(40, thumb_width // 5)
        y_step = max(32, thumb_height // 4)
        for candidate_top in range(top, bottom - thumb_height + 1, y_step):
            for candidate_left in range(left, right - thumb_width + 1, x_step):
                box = (
                    candidate_left,
                    candidate_top,
                    candidate_left + thumb_width,
                    candidate_top + thumb_height,
                )
                score = _score_thumbnail_box(image, box)
                if score < 30:
                    continue
                candidate = {
                    "left": candidate_left + origin_x,
                    "top": candidate_top + origin_y,
                    "right": candidate_left + thumb_width + origin_x,
                    "bottom": candidate_top + thumb_height + origin_y,
                    "center_x": candidate_left + thumb_width // 2 + origin_x,
                    "center_y": candidate_top + thumb_height // 2 + origin_y,
                    "score": round(score, 2),
                }
                if _is_unsafe_screen_edge_candidate(
                    candidate,
                    image_width,
                    image_height,
                    origin_x,
                    origin_y,
                ):
                    continue
                candidates.append(
                    candidate
                )
    return candidates


def _is_unsafe_screen_edge_candidate(
    candidate: dict[str, Any],
    image_width: int,
    image_height: int,
    origin_x: int,
    origin_y: int,
) -> bool:
    relative_center_x = candidate["center_x"] - origin_x
    relative_center_y = candidate["center_y"] - origin_y
    return (
        relative_center_x < image_width * 0.06
        or relative_center_y < image_height * 0.10
    )


def _score_thumbnail_box(image: Any, box: tuple[int, int, int, int]) -> float:
    sample = image.crop(box).resize((48, 27))
    stat = ImageStat.Stat(sample)
    channel_stddev = sum(float(value) for value in stat.stddev)
    if hasattr(sample, "get_flattened_data"):
        pixels = list(sample.get_flattened_data())
    else:
        pixels = list(sample.getdata())
    if not pixels:
        return 0.0

    brightness_values = [(red + green + blue) / 3 for red, green, blue in pixels]
    mean_brightness = sum(brightness_values) / len(brightness_values)
    white_ratio = sum(1 for value in brightness_values if value > 238) / len(brightness_values)
    gray_ratio = sum(
        1 for red, green, blue in pixels if max(red, green, blue) - min(red, green, blue) < 8
    ) / len(pixels)
    colorfulness = sum(max(pixel) - min(pixel) for pixel in pixels) / len(pixels)

    score = channel_stddev + colorfulness * 0.55
    if white_ratio > 0.55:
        score -= (white_ratio - 0.55) * 120
    if gray_ratio > 0.85:
        score -= (gray_ratio - 0.85) * 90
    if mean_brightness < 18 or mean_brightness > 248:
        score -= 35
    return score


def _dedupe_thumbnail_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        if any(_candidate_overlap(candidate, existing) > 0.35 for existing in kept):
            continue
        kept.append(candidate)
    return sorted(kept, key=lambda item: (item["top"], item["left"]))[:12]


def _candidate_overlap(first: dict[str, Any], second: dict[str, Any]) -> float:
    left = max(first["left"], second["left"])
    top = max(first["top"], second["top"])
    right = min(first["right"], second["right"])
    bottom = min(first["bottom"], second["bottom"])
    if right <= left or bottom <= top:
        return 0.0

    intersection = (right - left) * (bottom - top)
    first_area = (first["right"] - first["left"]) * (first["bottom"] - first["top"])
    second_area = (second["right"] - second["left"]) * (second["bottom"] - second["top"])
    return intersection / max(1, min(first_area, second_area))


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_browser_target(target: str) -> str:
    cleaned = target.strip().strip("\"'")
    lowered = cleaned.lower()
    if lowered in SITE_ALIASES:
        return SITE_ALIASES[lowered]

    parsed = urlparse(cleaned)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("browser_open only supports http and https URLs.")
        if not parsed.netloc:
            raise ValueError("browser_open requires a valid URL host.")
        return cleaned

    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"

    return f"https://www.bing.com/search?q={quote_plus(cleaned)}"


def _ratio(value: Any, name: str) -> float:
    try:
        ratio = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number between 0 and 1.") from exc
    if ratio < 0 or ratio > 1:
        raise ValueError(f"{name} must be between 0 and 1.")
    return ratio


def build_youtube_url(
    action: str,
    query: str = "",
    video_url: str = "",
    video_id: str = "",
) -> tuple[str, str, str | None]:
    if video_url:
        return normalize_youtube_url(video_url), "video", None
    if video_id:
        return f"https://www.youtube.com/watch?v={quote_plus(video_id)}", "video", None

    if action in {"home", "open"}:
        return "https://www.youtube.com", "home", None
    if action in {"random", "random_video", "recommended", "recommendation"}:
        return "https://www.youtube.com", "random", query or None
    if action in {"search", "specific", "video", "play", "watch"}:
        if not query:
            raise ValueError("youtube_open requires query, video_url, or video_id for this action.")
        return youtube_search_url(query), "search", query

    raise ValueError(
        "youtube_open action must be one of home, search, video, play, watch, or random."
    )


def youtube_search_url(query: str) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("YouTube search query cannot be empty.")
    return f"https://www.youtube.com/results?search_query={quote_plus(cleaned)}"


def normalize_youtube_url(raw_url: str) -> str:
    cleaned = raw_url.strip().strip("\"'")
    parsed = urlparse(cleaned)
    if not parsed.scheme:
        cleaned = f"https://{cleaned}"
        parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("youtube_open only supports http and https YouTube URLs.")

    host = parsed.netloc.lower()
    if host not in YOUTUBE_HOSTS:
        raise ValueError("youtube_open only accepts YouTube URLs.")
    return cleaned
