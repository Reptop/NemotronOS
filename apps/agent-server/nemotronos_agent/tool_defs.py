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
            "name": "ui_find",
            "description": "Find UI elements on the current screen.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
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
            "name": "app_launch",
            "description": "Launch an application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "enum": ["notepad", "calculator", "calc", "paint", "mspaint"],
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
                },
                "required": ["action"],
            },
        },
        {
            "name": "youtube_click_video",
            "description": (
                "Click a visible YouTube video in the foreground browser window using "
                "a screen-coordinate heuristic. Use first_result after YouTube search "
                "pages and random_visible after the YouTube home/recommendations page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selection": {
                        "type": "string",
                        "enum": ["first_result", "random_visible"],
                    },
                    "wait_seconds": {"type": "number"},
                },
                "required": ["selection"],
            },
        },
        {
            "name": "browser_click_text",
            "description": "Click a text element in the browser.",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
        },
        {
            "name": "browser_type",
            "description": "Type text into a browser input.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}, "text": {"type": "string"}},
            },
        },
        {
            "name": "browser_extract_page",
            "description": "Extract structured text from the current browser page.",
            "parameters": {"type": "object", "properties": {}},
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
        {
            "name": "user_confirm",
            "description": "Request human approval before continuing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "risk_level": {"type": "string"},
                },
            },
        },
    ]
