"""
Windows 11 Clipchamp Environment Scanner & Project Importer/Exporter.
Integrates with Windows 11 Microsoft Clipchamp local storage, user configuration,
and portable project schema.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from clipchamp_studio.model.project import ClipchampProject


def get_clipchamp_appdata_dir() -> Optional[Path]:
    """Locate Windows 11 Microsoft Clipchamp UWP/PWA data folder."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None

    packages_dir = Path(local_appdata) / "Packages"
    if not packages_dir.exists():
        return None

    for child in packages_dir.iterdir():
        if child.is_dir() and "Clipchamp.Clipchamp" in child.name:
            return child
    return None


def scan_clipchamp_status() -> Dict[str, Any]:
    """
    Analyze local Windows 11 Clipchamp installation status,
    user settings, and cached assets.
    """
    clipchamp_dir = get_clipchamp_appdata_dir()
    status: Dict[str, Any] = {
        "is_installed": clipchamp_dir is not None and clipchamp_dir.exists(),
        "package_path": str(clipchamp_dir) if clipchamp_dir else None,
        "user_settings_found": False,
        "user_settings": {},
        "discovered_projects": [],
    }

    if not clipchamp_dir or not clipchamp_dir.exists():
        return status

    # Check user settings json
    settings_file = clipchamp_dir / "LocalState" / "clipchamp.user-settings.json"
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8", errors="ignore") as f:
                settings_data = json.load(f)
                status["user_settings_found"] = True
                status["user_settings"] = settings_data
        except Exception:
            pass

    return status


def import_clipchamp_project(file_path: Path) -> ClipchampProject:
    """Import a Clipchamp JSON manifest or exported studio project."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Project file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Detect if format is our native project or Clipchamp schema
    if "video_clips" in data:
        return ClipchampProject.from_dict(data)

    # Convert generic Clipchamp schema if different
    proj = ClipchampProject(
        project_name=data.get("title", data.get("name", file_path.stem)),
    )
    return proj

