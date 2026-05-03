from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .desktop_actions import (
    CanvasCourseLookupError,
    find_canvas_course_via_api,
    normalize_canvas_base_url,
)


def canvas_list_assignments_due_soon(
    arguments: dict[str, Any],
    canvas_base_url: str,
    canvas_api_token: str,
) -> dict[str, Any]:
    base_url = normalize_canvas_base_url(canvas_base_url)
    days_ahead = _positive_int(arguments.get("days_ahead"), default=7, maximum=30)
    include_completed = bool(arguments.get("include_completed", False))
    course_query = str(arguments.get("course_query") or "").strip()
    course_ids = _course_ids(arguments.get("course_ids") or arguments.get("course_id"))

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=days_ahead)
    base_result = {
        "site": "canvas",
        "action": "list_assignments_due_soon",
        "canvas_base_url": base_url,
        "days_ahead": days_ahead,
        "include_completed": include_completed,
        "window_start": now.isoformat(),
        "window_end": window_end.isoformat(),
    }

    if not canvas_api_token.strip():
        return {
            **base_result,
            "assignments": [],
            "assignment_count": 0,
            "courses_checked": [],
            "needs_canvas_api_token": True,
            "message": (
                "CANVAS_API_TOKEN is required to list Canvas assignments through the API."
            ),
        }

    try:
        courses = _resolve_courses(
            base_url=base_url,
            canvas_api_token=canvas_api_token,
            course_ids=course_ids,
            course_query=course_query,
        )
        assignments, course_errors = _list_due_assignments(
            base_url=base_url,
            canvas_api_token=canvas_api_token,
            courses=courses,
            now=now,
            window_end=window_end,
            include_completed=include_completed,
        )
    except CanvasAssignmentLookupError as exc:
        return {
            **base_result,
            "assignments": [],
            "assignment_count": 0,
            "courses_checked": [],
            "lookup_error": str(exc),
        }

    return {
        **base_result,
        "assignments": assignments,
        "assignment_count": len(assignments),
        "courses_checked": [
            {
                "id": str(course["id"]),
                "name": str(course.get("name") or course.get("course_code") or ""),
            }
            for course in courses
        ],
        **({"course_lookup_errors": course_errors} if course_errors else {}),
    }


class CanvasAssignmentLookupError(RuntimeError):
    pass


def _resolve_courses(
    base_url: str,
    canvas_api_token: str,
    course_ids: list[str],
    course_query: str,
) -> list[dict[str, Any]]:
    if course_ids:
        active_courses = _fetch_active_courses(base_url, canvas_api_token)
        by_id = {str(course.get("id")): course for course in active_courses}
        return [
            by_id.get(course_id, {"id": course_id, "name": f"Canvas course {course_id}"})
            for course_id in course_ids
        ]

    if course_query:
        try:
            match = find_canvas_course_via_api(
                course_query=course_query,
                canvas_base_url=base_url,
                canvas_api_token=canvas_api_token,
            )
        except (CanvasCourseLookupError, ValueError) as exc:
            raise CanvasAssignmentLookupError(str(exc)) from exc
        if not match:
            raise CanvasAssignmentLookupError(
                f"No active Canvas course matched '{course_query}'."
            )
        return [
            {
                "id": match["id"],
                "name": match.get("name") or match.get("course_code") or course_query,
            }
        ]

    courses = _fetch_active_courses(base_url, canvas_api_token)
    if not courses:
        raise CanvasAssignmentLookupError("Canvas API returned no active courses.")
    return courses


def _fetch_active_courses(base_url: str, canvas_api_token: str) -> list[dict[str, Any]]:
    payload = _canvas_get_pages(
        base_url,
        canvas_api_token,
        "/api/v1/courses",
        {
            "enrollment_state": "active",
            "include[]": ["term"],
            "per_page": 100,
        },
    )
    courses = [
        course
        for course in payload
        if isinstance(course, dict) and course.get("id") is not None
    ]
    return courses


def _list_due_assignments(
    base_url: str,
    canvas_api_token: str,
    courses: list[dict[str, Any]],
    now: datetime,
    window_end: datetime,
    include_completed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    assignments: list[dict[str, Any]] = []
    course_errors: list[dict[str, str]] = []
    for course in courses:
        course_id = str(course["id"])
        course_name = str(course.get("name") or course.get("course_code") or course_id)
        try:
            payload = _canvas_get_pages(
                base_url,
                canvas_api_token,
                f"/api/v1/courses/{course_id}/assignments",
                {
                    "bucket": "upcoming",
                    "include[]": ["submission"],
                    "order_by": "due_at",
                    "per_page": 100,
                },
            )
        except CanvasAssignmentLookupError as exc:
            course_errors.append(
                {
                    "course_id": course_id,
                    "course_name": course_name,
                    "error": str(exc),
                }
            )
            continue
        for raw_assignment in payload:
            if not isinstance(raw_assignment, dict):
                continue
            normalized = _normalize_assignment(
                raw_assignment,
                course_id=course_id,
                course_name=course_name,
                now=now,
                window_end=window_end,
                include_completed=include_completed,
            )
            if normalized:
                assignments.append(normalized)

    return (
        sorted(assignments, key=lambda item: (item["due_at"], item["course_name"], item["name"])),
        course_errors,
    )


def _normalize_assignment(
    assignment: dict[str, Any],
    course_id: str,
    course_name: str,
    now: datetime,
    window_end: datetime,
    include_completed: bool,
) -> dict[str, Any] | None:
    due_at = _parse_canvas_datetime(assignment.get("due_at"))
    if due_at is None or due_at < now or due_at > window_end:
        return None
    if not include_completed and _assignment_submitted(assignment):
        return None

    return {
        "id": str(assignment.get("id") or ""),
        "course_id": course_id,
        "course_name": course_name,
        "name": str(assignment.get("name") or "Untitled assignment"),
        "due_at": due_at.isoformat(),
        "due_display": _format_due_display(due_at),
        "url": str(assignment.get("html_url") or ""),
        "points_possible": assignment.get("points_possible"),
        "submitted": _assignment_submitted(assignment),
    }


def _canvas_get_pages(
    base_url: str,
    canvas_api_token: str,
    path: str,
    params: dict[str, Any],
) -> list[Any]:
    url = _canvas_url(base_url, path, params)
    payload: list[Any] = []
    for _ in range(5):
        page, next_url = _canvas_get(url, canvas_api_token)
        if not isinstance(page, list):
            raise CanvasAssignmentLookupError("Canvas API returned an unexpected payload.")
        payload.extend(page)
        if not next_url:
            break
        url = next_url
    return payload


def _canvas_get(url: str, canvas_api_token: str) -> tuple[Any, str | None]:
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {canvas_api_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, _next_link(response.headers.get("Link", ""))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {detail[:200]}" if detail else ""
        raise CanvasAssignmentLookupError(
            f"Canvas API lookup failed with HTTP {exc.code}{suffix}"
        ) from exc
    except URLError as exc:
        raise CanvasAssignmentLookupError(f"Canvas API lookup failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise CanvasAssignmentLookupError("Canvas API lookup timed out.") from exc
    except json.JSONDecodeError as exc:
        raise CanvasAssignmentLookupError("Canvas API returned non-JSON data.") from exc


def _canvas_url(base_url: str, path: str, params: dict[str, Any]) -> str:
    query = urlencode(params, doseq=True)
    return f"{base_url}{path}?{query}"


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        start = part.find("<")
        end = part.find(">", start + 1)
        if start >= 0 and end > start:
            return part[start + 1 : end]
    return None


def _parse_canvas_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_due_display(due_at: datetime) -> str:
    local_due = due_at.astimezone()
    return local_due.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")


def _assignment_submitted(assignment: dict[str, Any]) -> bool:
    submission = assignment.get("submission")
    if not isinstance(submission, dict):
        return False
    workflow_state = str(submission.get("workflow_state") or "").lower()
    return bool(submission.get("submitted_at")) or workflow_state in {
        "submitted",
        "graded",
        "pending_review",
    }


def _positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _course_ids(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        values = raw_value
    else:
        values = str(raw_value).split(",")
    return [str(value).strip() for value in values if str(value).strip()]
