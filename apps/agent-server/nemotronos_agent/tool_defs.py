from __future__ import annotations

from typing import Any


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "fs_plan_changes",
            "description": "Dry-run filesystem organization inside the fake Windows sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root_path": {"type": "string"},
                    "goal": {"type": "string"},
                    "allowed_operations": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["mkdir", "move", "copy", "rename"],
                        },
                    },
                },
                "required": ["root_path", "goal", "allowed_operations"],
            },
        },
        {
            "name": "fs_apply_changes",
            "description": "Apply a previously generated filesystem plan inside the sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                    "create_undo_log": {"type": "boolean"},
                },
                "required": ["plan_id", "create_undo_log"],
            },
        },
        {
            "name": "screen_capture",
            "description": "Capture the current desktop view.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "mouse_click",
            "description": "Click on a UI target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "x_ratio": {"type": "number"},
                    "y_ratio": {"type": "number"},
                },
            },
        },
        {
            "name": "keyboard_type",
            "description": "Type text into the active UI element.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
        {
            "name": "discord_send_message",
            "description": (
                "Send a message to the currently active Discord conversation. "
                "This focuses/opens Discord, pastes text into the active chat input, "
                "and presses Enter without selecting servers or channels."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "open_if_needed": {"type": "boolean"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "app_launch",
            "description": "Launch an application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "enum": [
                            "notepad",
                            "calculator",
                            "calc",
                            "paint",
                            "mspaint",
                            "discord",
                        ],
                    }
                },
                "required": ["app_name"],
            },
        },
        {
            "name": "shell_run",
            "description": "Run a shell command through the tool server.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
        {
            "name": "browser_open",
            "description": (
                "Open the user's default web browser to an http(s) URL, domain, "
                "or common site name such as canvas."
            ),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "browser_session_ensure",
            "description": (
                "Ensure the managed Chrome browser automation session exists and return a "
                "structured snapshot of the current page. Optionally start at a URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {"start_url": {"type": "string"}},
            },
        },
        {
            "name": "browser_navigate",
            "description": (
                "Navigate the managed Chrome browser automation page to an http(s) URL or domain "
                "and return a structured page snapshot."
            ),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "browser_snapshot",
            "description": (
                "Return a structured snapshot of the current managed browser page, including "
                "visible text and actionable target ids."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_text_chars": {"type": "integer"},
                    "max_targets": {"type": "integer"},
                },
            },
        },
        {
            "name": "browser_click",
            "description": "Click an actionable browser target from the latest page snapshot.",
            "parameters": {
                "type": "object",
                "properties": {"target_id": {"type": "string"}},
                "required": ["target_id"],
            },
        },
        {
            "name": "browser_type",
            "description": "Type text into a browser input target from the latest page snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {"type": "string"},
                    "text": {"type": "string"},
                    "clear_first": {"type": "boolean"},
                },
                "required": ["target_id", "text"],
            },
        },
        {
            "name": "browser_select_option",
            "description": "Select an option in a browser select target from the latest page snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {"type": "string"},
                    "value_or_label": {"type": "string"},
                },
                "required": ["target_id", "value_or_label"],
            },
        },
        {
            "name": "browser_press",
            "description": "Press a keyboard key in the managed browser page.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
        {
            "name": "gmail_open",
            "description": (
                "Open Gmail in the managed Chrome automation session and return a DOM snapshot. "
                "Use this for inbox, sent, drafts, starred, or all-mail navigation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "view": {
                        "type": "string",
                        "enum": ["inbox", "sent", "drafts", "starred", "all"],
                    }
                },
            },
        },
        {
            "name": "gmail_search",
            "description": (
                "Search Gmail in the managed Chrome automation session and return a DOM snapshot "
                "of the result page. This reads existing mail state only."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "gmail_compose_draft",
            "description": (
                "Compose a Gmail draft without sending it. "
                "For send-email requests, call this first to create the draft, then call "
                "gmail_send_current_draft only after explicit user approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "body"],
            },
        },
        {
            "name": "gmail_send_current_draft",
            "description": (
                "Send the currently open Gmail compose draft. "
                "This is a high-impact external action and must only be used after "
                "the draft has been composed and the user explicitly approves sending it."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "youtube_open",
            "description": (
                "Open YouTube home, search YouTube for a requested video/title, "
                "open an exact YouTube video URL or video id, or open a randomized "
                "YouTube topic search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["home", "search", "video", "play", "watch", "random"],
                    },
                    "query": {"type": "string"},
                    "video_url": {"type": "string"},
                    "video_id": {"type": "string"},
                    "prefer_video_results": {"type": "boolean"},
                },
                "required": ["action"],
            },
        },
        {
            "name": "youtube_click_video",
            "description": (
                "Click a visible YouTube video in the foreground browser window using "
                "a screen-coordinate heuristic. Use first_video_result after YouTube search "
                "pages and random_visible after the YouTube home/recommendations page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selection": {
                        "type": "string",
                        "enum": ["first_result", "first_video_result", "random_visible"],
                    },
                    "wait_seconds": {"type": "number"},
                },
                "required": ["selection"],
            },
        },
        {
            "name": "canvas_open_course",
            "description": (
                "Open Canvas and navigate to a requested course. If a configured "
                "course alias or Canvas API token is available, open the exact course; "
                "otherwise open the user's Canvas courses page."
            ),
            "parameters": {
                "type": "object",
                "properties": {"course_query": {"type": "string"}},
                "required": ["course_query"],
            },
        },
        {
            "name": "notify_user",
            "description": "Send a user-facing notification.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        },
    ]
