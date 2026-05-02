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
            "parameters": {"type": "object", "properties": {"target": {"type": "string"}}},
        },
        {
            "name": "keyboard_type",
            "description": "Type text into the active UI element.",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
        },
        {
            "name": "app_launch",
            "description": "Launch an application.",
            "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}},
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
            "description": "Open a browser to a URL.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
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
