from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..path_mapper import FakeWindowsPathMapper, SandboxPathError
from ..plan_store import PlanStore


FILE_TYPE_FOLDERS: dict[str, str] = {
    ".png": "Images",
    ".jpg": "Images",
    ".jpeg": "Images",
    ".gif": "Images",
    ".bmp": "Images",
    ".pdf": "PDFs",
    ".txt": "Text",
    ".md": "Text",
    ".zip": "Archives",
    ".csv": "Data",
    ".tsv": "Data",
}


DEMO_DOWNLOAD_FILES: dict[str, str] = {
    "invoice_april.pdf": "Mock PDF content for invoice_april.pdf\n",
    "project_notes.txt": "Project notes placeholder text.\n",
    "random.zip": "Mock archive placeholder data.\n",
    "resume.pdf": "Mock PDF content for resume.pdf\n",
    "screenshot_001.png": "mock image placeholder for screenshot_001.png\n",
    "screenshot_002.png": "mock image placeholder for screenshot_002.png\n",
    "wildfire_dataset.csv": "region,acres,status\nNorth,1200,active\nSouth,220,contained\n",
}


class FilesystemToolService:
    def __init__(self, path_mapper: FakeWindowsPathMapper, plan_store: PlanStore) -> None:
        self.path_mapper = path_mapper
        self.plan_store = plan_store

    def fs_plan_changes(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root_path = str(arguments.get("root_path", "")).strip()
        goal = str(arguments.get("goal", "")).strip()
        allowed_operations = [
            str(operation).strip().lower()
            for operation in arguments.get("allowed_operations", [])
        ]

        if not root_path:
            raise ValueError("fs_plan_changes requires root_path.")
        if not goal:
            raise ValueError("fs_plan_changes requires goal.")
        if "move" not in allowed_operations:
            raise ValueError("fs_plan_changes requires 'move' in allowed_operations.")
        if "mkdir" not in allowed_operations:
            raise ValueError("fs_plan_changes requires 'mkdir' in allowed_operations.")

        local_root = self.path_mapper.to_local_path(root_path)
        if not local_root.exists():
            raise ValueError(f"Root path does not exist: {root_path}")
        if not local_root.is_dir():
            raise ValueError(f"Root path is not a directory: {root_path}")

        proposed_changes: list[dict[str, Any]] = []
        directories_to_create: set[Path] = set()
        planned_files = 0

        for candidate in sorted(local_root.iterdir(), key=lambda item: item.name.lower()):
            if not candidate.is_file():
                continue

            target_folder = self._target_folder_for(candidate)
            destination_dir = local_root / target_folder
            destination_file = destination_dir / candidate.name

            if candidate.parent == destination_dir:
                continue

            directories_to_create.add(destination_dir)
            proposed_changes.append(
                {
                    "operation": "move",
                    "source": self.path_mapper.to_windows_path(candidate),
                    "destination": self.path_mapper.to_windows_path(destination_file),
                    "reason": f"Group {candidate.name} into {target_folder}.",
                    "category": target_folder,
                }
            )
            planned_files += 1

        for directory in sorted(directories_to_create, key=lambda item: item.name.lower()):
            if directory.exists():
                continue
            proposed_changes.insert(
                0,
                {
                    "operation": "mkdir",
                    "path": self.path_mapper.to_windows_path(directory),
                    "reason": f"Create the {directory.name} folder for grouped files.",
                },
            )

        stored_plan = self.plan_store.create_plan(
            {
                "root_path": root_path,
                "goal": goal,
                "allowed_operations": allowed_operations,
                "proposed_changes": proposed_changes,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "files_considered": planned_files,
                    "changes_count": len(proposed_changes),
                },
            }
        )

        return stored_plan

    def fs_apply_changes(self, arguments: dict[str, Any]) -> dict[str, Any]:
        plan_id = str(arguments.get("plan_id", "")).strip()
        create_undo_log = bool(arguments.get("create_undo_log", False))
        if not plan_id:
            raise ValueError("fs_apply_changes requires plan_id.")

        stored_plan = self.plan_store.get_plan(plan_id)
        if not stored_plan:
            raise ValueError(f"Plan not found: {plan_id}")

        applied_changes: list[dict[str, Any]] = []
        undo_operations: list[dict[str, Any]] = []

        for change in stored_plan["proposed_changes"]:
            operation = change["operation"]
            if operation == "mkdir":
                target_dir = self.path_mapper.to_local_path(change["path"])
                target_dir.mkdir(parents=True, exist_ok=True)
                applied_changes.append(change)
                continue

            if operation == "move":
                source = self.path_mapper.to_local_path(change["source"])
                destination = self.path_mapper.to_local_path(change["destination"])
                destination.parent.mkdir(parents=True, exist_ok=True)

                if not source.exists():
                    raise ValueError(f"Source file no longer exists: {change['source']}")

                shutil.move(str(source), str(destination))
                applied_changes.append(change)
                undo_operations.append(
                    {
                        "operation": "move",
                        "source": change["destination"],
                        "destination": change["source"],
                    }
                )
                continue

            raise ValueError(f"Unsupported operation in stored plan: {operation}")

        undo_log_path: str | None = None
        if create_undo_log:
            undo_log_path = self._write_undo_log(stored_plan, undo_operations)

        return {
            "plan_id": plan_id,
            "applied_changes": applied_changes,
            "undo_log_path": undo_log_path,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }

    def reset_demo_downloads(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root_path = str(arguments.get("root_path", "")).strip()
        if not root_path:
            raise ValueError("reset_demo_downloads requires root_path.")

        local_root = self.path_mapper.to_local_path(root_path)
        local_root.mkdir(parents=True, exist_ok=True)

        removed_paths: list[str] = []
        created_files: list[str] = []

        for directory_name in sorted(set(FILE_TYPE_FOLDERS.values()) | {"Other"}):
            directory = local_root / directory_name
            if directory.exists():
                shutil.rmtree(directory)
                removed_paths.append(self.path_mapper.to_windows_path(directory))

        undo_root = self.path_mapper.to_local_path(r"C:\.nemotronos")
        if undo_root.exists():
            shutil.rmtree(undo_root)
            removed_paths.append(self.path_mapper.to_windows_path(undo_root))

        for file_name, content in DEMO_DOWNLOAD_FILES.items():
            file_path = local_root / file_name
            file_path.write_text(content, encoding="utf-8")
            created_files.append(self.path_mapper.to_windows_path(file_path))

        return {
            "root_path": root_path,
            "created_files": created_files,
            "removed_paths": removed_paths,
            "reset_at": datetime.now(timezone.utc).isoformat(),
        }

    def _target_folder_for(self, file_path: Path) -> str:
        return FILE_TYPE_FOLDERS.get(file_path.suffix.lower(), "Other")

    def _write_undo_log(
        self, stored_plan: dict[str, Any], undo_operations: list[dict[str, Any]]
    ) -> str:
        undo_dir = self.path_mapper.to_local_path(r"C:\.nemotronos\undo_logs")
        undo_dir.mkdir(parents=True, exist_ok=True)

        local_undo_file = undo_dir / f"{stored_plan['plan_id']}.json"
        payload = {
            "plan_id": stored_plan["plan_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "root_path": stored_plan["root_path"],
            "undo_operations": undo_operations,
        }
        local_undo_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.path_mapper.to_windows_path(local_undo_file)
