"""
Microsoft Windows 11 Clipchamp Studio Video Editor.
Complete desktop editing environment with multi-track timeline, real-time preview,
media asset drawer, property inspector, and Host GPU chunked export.
"""

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from clipchamp_studio.model.clipchamp_parser import import_clipchamp_project, scan_clipchamp_status
from clipchamp_studio.model.project import ClipchampProject
from clipchamp_studio.ui.export_dialog import ExportDialog
from clipchamp_studio.ui.inspector_widget import InspectorWidget
from clipchamp_studio.ui.media_pool_widget import MediaPoolWidget
from clipchamp_studio.ui.preview_canvas import VideoPreviewCanvas
from clipchamp_studio.ui.timeline_widget import InteractiveTimeline
from common.config import DEFAULT_CLIENT_TARGET, DEFAULT_PORT, TEST_MEDIA_DIR

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ClipchampEditorWindow(ctk.CTk):
    """Main Application Window for Clipchamp Video Editor Studio."""

    def __init__(
        self,
        target_host: str = DEFAULT_CLIENT_TARGET,
        target_port: int = DEFAULT_PORT,
    ):
        super().__init__()
        self.target_host = target_host
        self.target_port = target_port

        self.title("Microsoft Windows 11 Clipchamp Studio — Distributed GPU Offloader")
        self.geometry("1340x880")
        self.minsize(1180, 760)

        # Initialize Default Project
        self.project = ClipchampProject(project_name="My Clipchamp Video Project")

        self._build_ui()
        self._load_initial_samples_if_available()

    def _build_ui(self):
        # 1. Top Titlebar / Command Strip
        self.top_bar = ctk.CTkFrame(self, height=52, corner_radius=0, fg_color="#0f172a")
        self.top_bar.pack(fill="x", side="top")

        # Logo & App Title
        lbl_app = ctk.CTkLabel(
            self.top_bar,
            text="🎬 CLIPCHAMP STUDIO",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#818cf8",
        )
        lbl_app.pack(side="left", padx=14)

        # Project Name input
        self.entry_title = ctk.CTkEntry(
            self.top_bar,
            width=230,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.entry_title.insert(0, self.project.project_name)
        self.entry_title.pack(side="left", padx=10)
        self.entry_title.bind("<KeyRelease>", self._on_title_change)

        # File Actions
        self.btn_open_proj = ctk.CTkButton(
            self.top_bar,
            text="📂 Open",
            width=70,
            height=28,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._on_open_project,
        )
        self.btn_open_proj.pack(side="left", padx=4)

        self.btn_save_proj = ctk.CTkButton(
            self.top_bar,
            text="💾 Save",
            width=70,
            height=28,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._on_save_project,
        )
        self.btn_save_proj.pack(side="left", padx=4)

        self.btn_scan_win11 = ctk.CTkButton(
            self.top_bar,
            text="🔍 Scan Win11 Clipchamp",
            width=165,
            height=28,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._on_scan_clipchamp_env,
        )
        self.btn_scan_win11.pack(side="left", padx=6)

        self.btn_open_transcoder = ctk.CTkButton(
            self.top_bar,
            text="⚡ Transcoder Hub",
            width=135,
            height=28,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._on_open_transcoder,
        )
        self.btn_open_transcoder.pack(side="left", padx=6)

        # Host Worker Connection Badge & Config
        self.host_entry = ctk.CTkEntry(
            self.top_bar,
            width=115,
            height=28,
            placeholder_text="127.0.0.1",
        )
        self.host_entry.insert(0, self.target_host)
        self.host_entry.pack(side="right", padx=(4, 14))

        lbl_h = ctk.CTkLabel(
            self.top_bar,
            text="Host IP:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8",
        )
        lbl_h.pack(side="right", padx=(0, 4))

        # Big Glowing "Export with Host GPU" Button
        self.btn_export_gpu = ctk.CTkButton(
            self.top_bar,
            text="🚀 Export with Host GPU",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#6366f1",
            hover_color="#4f46e5",
            height=32,
            command=self._open_export_dialog,
        )
        self.btn_export_gpu.pack(side="right", padx=10)

        # 2. Main Middle Workspace (3 Columns: Left Media / Center Preview / Right Inspector)
        self.workspace_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.workspace_frame.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        # Left Column: Media Pool Drawer
        self.media_pool = MediaPoolWidget(
            self.workspace_frame,
            project=self.project,
            width=280,
            on_clip_added=self._on_project_modified,
            get_playhead_time=lambda: self.timeline.playhead_time,
        )
        self.media_pool.pack(side="left", fill="y", padx=(0, 6))

        # Center Column: Preview Monitor Canvas
        self.preview_monitor = VideoPreviewCanvas(
            self.workspace_frame,
            project=self.project,
            on_playhead_change=self._on_preview_playhead_moved,
        )
        self.preview_monitor.pack(side="left", fill="both", expand=True, padx=4)

        # Right Column: Inspector Properties
        self.inspector = InspectorWidget(
            self.workspace_frame,
            project=self.project,
            width=290,
            on_project_modified=self._on_project_modified,
        )
        self.inspector.pack(side="right", fill="y", padx=(6, 0))

        # 3. Bottom Workspace: Multi-Track Interactive Timeline
        self.timeline = InteractiveTimeline(
            self,
            project=self.project,
            height=210,
            on_select_item=self._on_timeline_item_selected,
            on_playhead_move=self._on_timeline_playhead_moved,
            on_split_request=self._on_split_clip,
            on_delete_request=self._on_delete_item,
        )
        self.timeline.pack(fill="x", side="bottom", padx=10, pady=(4, 10))

    def _load_initial_samples_if_available(self):
        """Auto-populate the timeline with existing sample clips if timeline is empty."""
        if not self.project.video_clips and TEST_MEDIA_DIR.exists():
            samples = list(TEST_MEDIA_DIR.glob("*.mp4"))
            if samples:
                # Add first sample clip to timeline
                self.project.add_video_clip_from_file(samples[0])
                self.project.add_text_overlay("SAMPLE INTRO", timeline_start=0.0, duration=2.5)
                self._on_project_modified()

    def _on_title_change(self, event):
        self.project.project_name = self.entry_title.get()

    def _on_preview_playhead_moved(self, t: float):
        self.timeline.set_playhead_time(t)

    def _on_timeline_playhead_moved(self, t: float):
        self.preview_monitor.seek_to(t)

    def _on_timeline_item_selected(self, item_id: str, item_type: str):
        self.inspector.select_item(item_id, item_type)
        item = self.project.find_item_by_id(item_id)
        if item and hasattr(item, "timeline_start"):
            self.preview_monitor.seek_to(item.timeline_start)

    def _on_project_modified(self):
        """Refresh all synchronized UI views when project changes."""
        self.timeline.redraw()
        self.preview_monitor.set_project(self.project)
        self.inspector.set_project(self.project)

    def _on_split_clip(self, clip_id: str, split_time: float):
        if self.project.split_video_clip(clip_id, split_time):
            self._on_project_modified()

    def _on_delete_item(self, item_id: str):
        if self.project.remove_item(item_id):
            self.inspector.show_project_settings()
            self._on_project_modified()

    def _on_save_project(self):
        dest = filedialog.asksaveasfilename(
            title="Save Clipchamp Project",
            defaultextension=".clipchamp.json",
            filetypes=[("Clipchamp Project", "*.clipchamp.json"), ("JSON", "*.json")],
        )
        if dest:
            self.project.save_to_json(Path(dest))
            messagebox.showinfo("Project Saved", f"Saved project to:\n{dest}")

    def _on_open_project(self):
        src = filedialog.askopenfilename(
            title="Open Clipchamp Project",
            filetypes=[("Clipchamp Project", "*.clipchamp.json *.json"), ("All Files", "*.*")],
        )
        if src:
            try:
                self.project = import_clipchamp_project(Path(src))
                self.entry_title.delete(0, "end")
                self.entry_title.insert(0, self.project.project_name)
                self.media_pool.set_project(self.project)
                self._on_project_modified()
            except Exception as e:
                messagebox.showerror("Failed to open project", str(e))

    def _on_scan_clipchamp_env(self):
        """Detect local Windows 11 Clipchamp state."""
        status = scan_clipchamp_status()
        if status["is_installed"]:
            msg = (
                f"✅ Microsoft Windows 11 Clipchamp Detected!\n\n"
                f"Package Path:\n{status['package_path']}\n\n"
                f"User Settings Found: {status['user_settings_found']}\n"
                f"Ready to import / export projects and offload to Host GPU!"
            )
            messagebox.showinfo("Windows 11 Clipchamp Status", msg)
        else:
            messagebox.showinfo("Clipchamp Status", "Clipchamp package not detected in default UWP directory.")

    def _on_open_transcoder(self):
        from client.gui_app import DistributedOffloadGUI
        target_ip = self.host_entry.get().strip() or self.target_host
        app = DistributedOffloadGUI(target_ip=target_ip)
        app.mainloop()

    def _open_export_dialog(self):
        """Launch the Host GPU chunked export dialog."""
        target_ip = self.host_entry.get().strip() or self.target_host
        dlg = ExportDialog(
            parent=self,
            project=self.project,
            target_host=target_ip,
            target_port=self.target_port,
        )
        dlg.grab_set()


def main():
    app = ClipchampEditorWindow()
    app.mainloop()


if __name__ == "__main__":
    main()

