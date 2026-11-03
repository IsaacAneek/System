#!/usr/bin/env python3
"""
Dear ImGui NFS Explorer (Monkeytype Theme)
Searches for exported NFS shares via mDNS & showmount, provides one-click
mounting with interactive mount point configuration popups, and manages active OS mounts.
"""

import os
import sys
import time
import threading
from datetime import datetime

try:
    import dearpygui.dearpygui as dpg
except ImportError:
    print("\n" + "=" * 65)
    print(" [!] DearPyGui is not installed in the current Python environment.")
    print("     To run this GUI, please install dearpygui:")
    print("       pip install dearpygui --break-system-packages")
    print("     Or execute via the provided launcher:")
    print("       cd ~/Practice/System/gui && ./run.sh")
    print("=" * 65 + "\n")
    sys.exit(1)

from nfs_manager import NFSManager


class NFSGuiApp:
    def __init__(self):
        self.mgr = NFSManager()
        self.discovered_shares = []
        self.active_mounts = []
        self.selected_share_for_mount = None

        # Threading flags
        self.is_scanning = False

    def log(self, message, level="INFO"):
        now = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{now}] [{level}] {message}"
        if dpg.does_item_exist("log_box"):
            prev = dpg.get_value("log_box")
            new_text = f"{prev}\n{formatted}" if prev else formatted
            # Keep log manageable
            lines = new_text.splitlines()[-40:]
            dpg.set_value("log_box", "\n".join(lines))

    def setup_monkeytype_theme(self):
        """
        Applies the iconic Monkeytype color palette:
        - Canvas background: #323437 (50, 52, 55)
        - Panel background:  #2c2e31 (44, 46, 49)
        - Input field bg:    #242628 (36, 38, 40)
        - Primary font text: #d1d0c5 (209, 208, 197)
        - Muted secondary:   #646669 (100, 102, 105)
        - Signature Accent:  #e2b714 (226, 183, 20)  [Yellow/Gold]
        - Danger / Error:    #ca4754 (202, 71, 84)   [Muted Red]
        - Borders & dividers:#424549 (66, 69, 73)
        """
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                # Window & Backgrounds
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (50, 52, 55, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (44, 46, 49, 250))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_BorderShadow, (0, 0, 0, 0))

                # Frames & Inputs
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (50, 52, 55, 255))

                # Title & Tabs
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Tab, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (226, 183, 20, 180))
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, (226, 183, 20, 255))

                # Text
                dpg.add_theme_color(dpg.mvThemeCol_Text, (209, 208, 197, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (100, 102, 105, 255))

                # Buttons
                dpg.add_theme_color(dpg.mvThemeCol_Button, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (226, 183, 20, 180))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (226, 183, 20, 255))

                # Headers & Selection
                dpg.add_theme_color(dpg.mvThemeCol_Header, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (226, 183, 20, 200))

                # Tables
                dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, (100, 102, 105, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (50, 52, 55, 255))

                # Scrollbars & Misc
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (226, 183, 20, 180))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, (226, 183, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (226, 183, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (66, 69, 73, 255))

                # Rounding Styles
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 5)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 5)

        dpg.bind_theme(global_theme)

        # Highlight Yellow Button Theme
        with dpg.theme() as self.gold_btn_theme:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, (226, 183, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (241, 194, 50, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (200, 160, 15, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)

        # Danger / Unmount Red Button Theme
        with dpg.theme() as self.red_btn_theme:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, (202, 71, 84, 190))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (220, 80, 95, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (180, 50, 65, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)

    def trigger_scan_async(self):
        if self.is_scanning:
            return
        self.is_scanning = True
        dpg.set_value("status_text", "Scanning network (mDNS / showmount)...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            self.log("Starting network discovery (mDNS / DNS-SD / showmount)...")
            shares = self.mgr.scan_all_exports(progress_callback=lambda msg: self.log(msg))
            self.discovered_shares = shares
            self.log(f"Scan complete. Found {len(shares)} exported NFS share(s).")
        except Exception as e:
            self.log(f"Scan error: {e}", level="ERROR")
        finally:
            self.is_scanning = False
            self.refresh_ui_tables()

    def query_single_host(self, host):
        if not host:
            return
        self.log(f"Querying exports on: {host} via showmount...")
        shares = self.mgr.query_showmount(host.strip())
        if not shares:
            self.log(f"No exports found on {host} (or host unreachable).", level="WARN")
        else:
            self.log(f"Found {len(shares)} export(s) on {host}.")
            # Append new shares if not already in list
            existing_sources = {s.full_source for s in self.discovered_shares}
            for s in shares:
                if s.full_source not in existing_sources:
                    self.discovered_shares.append(s)
        self.refresh_ui_tables()

    def refresh_ui_tables(self):
        # 1. Update Active Mounts
        self.active_mounts = self.mgr.get_active_mounts()
        active_sources = {m.source: m.mount_point for m in self.active_mounts}

        # Clear and rebuild Discovered Shares Table
        if dpg.does_item_exist("shares_table"):
            dpg.delete_item("shares_table", children_only=True)

            # Table Header
            dpg.add_table_column(label="Status", width_fixed=True, init_width_or_weight=90, parent="shares_table")
            dpg.add_table_column(label="Host", width_fixed=True, init_width_or_weight=130, parent="shares_table")
            dpg.add_table_column(label="Remote Export Path", parent="shares_table")
            dpg.add_table_column(label="Allowed Clients", width_fixed=True, init_width_or_weight=140, parent="shares_table")
            dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=100, parent="shares_table")

            for idx, share in enumerate(self.discovered_shares):
                is_mounted = share.full_source in active_sources
                status_label = "Mounted" if is_mounted else "Available"
                status_color = (226, 183, 20) if is_mounted else (100, 200, 120)

                with dpg.table_row(parent="shares_table"):
                    dpg.add_text(status_label, color=status_color)
                    dpg.add_text(share.host)
                    dpg.add_text(share.export_path)
                    dpg.add_text(share.clients, color=(160, 160, 160))

                    if is_mounted:
                        mount_pt = active_sources[share.full_source]
                        btn = dpg.add_button(
                            label="Unmount",
                            user_data=mount_pt,
                            callback=lambda s, a, u: self.handle_unmount(u)
                        )
                        dpg.bind_item_theme(btn, self.red_btn_theme)
                    else:
                        btn = dpg.add_button(
                            label="Mount...",
                            user_data=share,
                            callback=lambda s, a, u: self.open_mount_modal(u)
                        )
                        dpg.bind_item_theme(btn, self.gold_btn_theme)

        # Clear and rebuild Active Mounts Table
        if dpg.does_item_exist("mounts_table"):
            dpg.delete_item("mounts_table", children_only=True)

            dpg.add_table_column(label="Remote Source", parent="mounts_table")
            dpg.add_table_column(label="Local Mount Point", parent="mounts_table")
            dpg.add_table_column(label="FS Type", width_fixed=True, init_width_or_weight=80, parent="mounts_table")
            dpg.add_table_column(label="Disk Capacity / Free", width_fixed=True, init_width_or_weight=180, parent="mounts_table")
            dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=100, parent="mounts_table")

            for m in self.active_mounts:
                with dpg.table_row(parent="mounts_table"):
                    dpg.add_text(m.source, color=(226, 183, 20))
                    dpg.add_text(m.mount_point)
                    dpg.add_text(m.fs_type, color=(160, 160, 160))
                    dpg.add_text(m.size_str)
                    btn = dpg.add_button(
                        label="Unmount",
                        user_data=m.mount_point,
                        callback=lambda s, a, u: self.handle_unmount(u)
                    )
                    dpg.bind_item_theme(btn, self.red_btn_theme)

        dpg.set_value("status_text", f"Active Mounts: {len(self.active_mounts)} | Discovered Shares: {len(self.discovered_shares)}")

    def open_mount_modal(self, share):
        """
        Opens a popup dialog allowing the user to select or edit the local mount point directory.
        """
        self.selected_share_for_mount = share

        # Generate a clean default local mount point
        clean_name = share.export_path.strip("/").replace("/", "_")
        default_mount = f"/mnt/nfs_{clean_name}" if clean_name else "/mnt/nfs_share"

        dpg.set_value("modal_source_text", share.full_source)
        dpg.set_value("modal_mount_point", default_mount)
        dpg.set_value("modal_error_text", "")
        dpg.configure_item("mount_modal", show=True)

    def handle_modal_confirm(self):
        share = self.selected_share_for_mount
        mount_point = dpg.get_value("modal_mount_point").strip()
        options = dpg.get_value("modal_options").strip()
        pwd = dpg.get_value("modal_sudo_pwd").strip() or None

        if not mount_point:
            dpg.set_value("modal_error_text", "Error: Mount point path cannot be empty.")
            return

        self.log(f"Attempting mount: {share.full_source} -> {mount_point}...")
        success, out = self.mgr.mount_share(share.full_source, mount_point, options=options, sudo_password=pwd)

        if success:
            self.log(f"Successfully mounted {share.full_source} to {mount_point}!")
            dpg.configure_item("mount_modal", show=False)
            self.refresh_ui_tables()
        else:
            self.log(f"Mount failed: {out}", level="ERROR")
            dpg.set_value("modal_error_text", f"Failed: {out}")

    def handle_unmount(self, mount_point):
        self.log(f"Attempting to unmount: {mount_point}...")
        success, out = self.mgr.unmount_share(mount_point)
        if success:
            self.log(f"Successfully unmounted {mount_point}.")
        else:
            self.log(f"Standard unmount failed, trying lazy unmount (-l): {out}", level="WARN")
            success_lazy, out_lazy = self.mgr.unmount_share(mount_point, lazy=True)
            if success_lazy:
                self.log(f"Lazy unmount succeeded for {mount_point}.")
            else:
                self.log(f"Unmount failed: {out_lazy}", level="ERROR")
        self.refresh_ui_tables()

    def build_gui(self):
        dpg.create_context()
        self.setup_monkeytype_theme()

        # Primary Full-Window Container
        with dpg.window(tag="primary_window"):
            # Header
            with dpg.group(horizontal=True):
                dpg.add_text("NFS MOUNT EXPLORER", color=(226, 183, 20))
                dpg.add_text("|", color=(100, 102, 105))
                dpg.add_text("mDNS & showmount discovery", color=(100, 102, 105))
                dpg.add_spacer(width=20)
                dpg.add_text("Ready", tag="status_text", color=(209, 208, 197))

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Toolbar Controls
            with dpg.group(horizontal=True):
                scan_btn = dpg.add_button(
                    label="Scan Network (mDNS/DNS-SD)",
                    callback=lambda: self.trigger_scan_async()
                )
                dpg.bind_item_theme(scan_btn, self.gold_btn_theme)

                dpg.add_button(
                    label="Refresh Mounts",
                    callback=lambda: self.refresh_ui_tables()
                )

                dpg.add_spacer(width=25)
                dpg.add_text("Direct Query:")
                dpg.add_input_text(tag="manual_host_input", default_value="pi02.local", width=160, hint="e.g. pi02.local")
                dpg.add_button(
                    label="Query Host",
                    callback=lambda: self.query_single_host(dpg.get_value("manual_host_input"))
                )

            dpg.add_spacer(height=10)

            # Tab Bar for Navigation
            with dpg.tab_bar():
                # Tab 1: Discovered NFS Exports
                with dpg.tab(label="Discovered Exports"):
                    with dpg.child_window(height=260, border=True):
                        with dpg.table(
                            tag="shares_table",
                            header_row=True,
                            borders_innerH=True,
                            borders_outerH=True,
                            borders_innerV=True,
                            borders_outerV=True,
                            row_background=True,
                            resizable=True
                        ):
                            dpg.add_table_column(label="Status", width_fixed=True, init_width_or_weight=90)
                            dpg.add_table_column(label="Host", width_fixed=True, init_width_or_weight=130)
                            dpg.add_table_column(label="Remote Export Path")
                            dpg.add_table_column(label="Allowed Clients", width_fixed=True, init_width_or_weight=140)
                            dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=100)

                # Tab 2: Active OS Mounts
                with dpg.tab(label="Active System Mounts"):
                    with dpg.child_window(height=260, border=True):
                        with dpg.table(
                            tag="mounts_table",
                            header_row=True,
                            borders_innerH=True,
                            borders_outerH=True,
                            borders_innerV=True,
                            borders_outerV=True,
                            row_background=True,
                            resizable=True
                        ):
                            dpg.add_table_column(label="Remote Source")
                            dpg.add_table_column(label="Local Mount Point")
                            dpg.add_table_column(label="FS Type", width_fixed=True, init_width_or_weight=80)
                            dpg.add_table_column(label="Disk Capacity / Free", width_fixed=True, init_width_or_weight=180)
                            dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=100)

            dpg.add_spacer(height=5)

            # Activity / Command Log Box
            with dpg.collapsing_header(label="Execution & Activity Log", default_open=True):
                dpg.add_input_text(
                    tag="log_box",
                    multiline=True,
                    readonly=True,
                    width=-1,
                    height=130,
                    default_value="[System] NFS Explorer initialized. Monkeytype theme loaded."
                )

        # -------------------------------------------------------------------
        # Mount Configuration Modal Popup
        # -------------------------------------------------------------------
        with dpg.window(
            tag="mount_modal",
            label="Attach NFS Mount Point",
            modal=True,
            show=False,
            no_resize=True,
            width=500,
            height=300
        ):
            dpg.add_text("Configure Local Mount Destination", color=(226, 183, 20))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_text("Remote Share:", color=(100, 102, 105))
                dpg.add_text("", tag="modal_source_text", color=(209, 208, 197))

            dpg.add_spacer(height=5)
            dpg.add_text("Local Mount Directory:")
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="modal_mount_point", width=360, default_value="/mnt/nfs_share")
                dpg.add_button(
                    label="Browse",
                    callback=lambda: dpg.show_item("file_dialog_id")
                )

            dpg.add_spacer(height=5)
            dpg.add_text("Mount Options:")
            dpg.add_input_text(tag="modal_options", width=-1, default_value="rw,sync,noatime,_netdev")

            dpg.add_spacer(height=5)
            dpg.add_text("Sudo Password (if required):")
            dpg.add_input_text(tag="modal_sudo_pwd", password=True, width=-1, hint="Leave empty if using polkit or passwordless sudo")

            dpg.add_text("", tag="modal_error_text", color=(202, 71, 84))
            dpg.add_spacer(height=10)

            with dpg.group(horizontal=True):
                confirm_btn = dpg.add_button(
                    label="Confirm & Mount",
                    callback=lambda: self.handle_modal_confirm()
                )
                dpg.bind_item_theme(confirm_btn, self.gold_btn_theme)

                dpg.add_button(
                    label="Cancel",
                    callback=lambda: dpg.configure_item("mount_modal", show=False)
                )

        # Directory Picker Dialog
        def _dir_selected_cb(sender, app_data):
            selected_path = app_data.get("file_path_name")
            if selected_path:
                dpg.set_value("modal_mount_point", selected_path)

        dpg.add_file_dialog(
            directory_selector=True,
            show=False,
            callback=_dir_selected_cb,
            tag="file_dialog_id",
            width=500,
            height=350
        )

        # Viewport Setup
        dpg.create_viewport(title="NFS Mount Explorer (Monkeytype Theme)", width=850, height=620)
        dpg.setup_dearpygui()
        dpg.set_primary_window("primary_window", True)
        dpg.show_viewport()

        # Initial populate
        self.refresh_ui_tables()
        self.trigger_scan_async()

        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    app = NFSGuiApp()
    app.build_gui()

