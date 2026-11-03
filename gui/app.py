#!/usr/bin/env python3
"""
Dear ImGui NFS Explorer (Monkeytype Theme)
Dynamic Network Discovery (nmap subnet scan, arp-scan + avahi-resolve, mDNS / DNS-SD),
multiline host targets input, file-based host loading, showmount inspection,
and interactive mount / unmount management.
"""

import os
import sys
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

        # Threading flag
        self.is_busy = False

    def log(self, message, level="INFO"):
        now = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{now}] [{level}] {message}"
        if dpg.does_item_exist("log_box"):
            prev = dpg.get_value("log_box")
            new_text = f"{prev}\n{formatted}" if prev else formatted
            lines = new_text.splitlines()[-50:]
            dpg.set_value("log_box", "\n".join(lines))

    def setup_monkeytype_theme(self):
        """
        Iconic Monkeytype color palette:
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
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (50, 52, 55, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (44, 46, 49, 250))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_BorderShadow, (0, 0, 0, 0))

                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (50, 52, 55, 255))

                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Tab, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (226, 183, 20, 180))
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, (226, 183, 20, 255))

                dpg.add_theme_color(dpg.mvThemeCol_Text, (209, 208, 197, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (100, 102, 105, 255))

                dpg.add_theme_color(dpg.mvThemeCol_Button, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (226, 183, 20, 180))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (226, 183, 20, 255))

                dpg.add_theme_color(dpg.mvThemeCol_Header, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (226, 183, 20, 200))

                dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, (100, 102, 105, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, (44, 46, 49, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (50, 52, 55, 255))

                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (36, 38, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (66, 69, 73, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (226, 183, 20, 180))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, (226, 183, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (226, 183, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (66, 69, 73, 255))

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

    # -----------------------------------------------------------------------
    # Target List Management (Text Field & File Loading)
    # -----------------------------------------------------------------------
    def get_current_target_hosts(self):
        text = dpg.get_value("targets_text_input") or ""
        return self.mgr.parse_hosts_text(text)

    def append_target_hosts(self, new_hosts):
        current_hosts = self.get_current_target_hosts()
        seen = set(current_hosts)
        added = []
        for h in new_hosts:
            if h not in seen:
                seen.add(h)
                current_hosts.append(h)
                added.append(h)

        dpg.set_value("targets_text_input", "\n".join(current_hosts))
        return added

    def load_hosts_from_file_cb(self):
        file_path = dpg.get_value("hosts_file_path").strip()
        if not file_path:
            self.log("Please specify a valid file path to load.", level="WARN")
            return
        try:
            hosts = self.mgr.load_hosts_from_file(file_path)
            added = self.append_target_hosts(hosts)
            self.log(f"Loaded {len(hosts)} host(s) from '{file_path}' ({len(added)} new targets added).")
        except Exception as e:
            self.log(f"Failed to load file: {e}", level="ERROR")

    # -----------------------------------------------------------------------
    # Scanning Actions
    # -----------------------------------------------------------------------
    def scan_nmap_async(self):
        if self.is_busy:
            return
        self.is_busy = True
        subnet = dpg.get_value("subnet_input").strip() or None
        scan_nfs_only = dpg.get_value("nmap_nfs_only_check")

        def _worker():
            try:
                dpg.set_value("status_text", "Running Nmap LAN scan...")
                results = self.mgr.scan_network_nmap(subnet=subnet, scan_nfs_port=scan_nfs_only, progress_cb=self.log)
                hostnames = [r["host"] for r in results]
                added = self.append_target_hosts(hostnames)
                self.log(f"Nmap scan complete. Discovered {len(results)} host(s) ({len(added)} new targets added).")

                # Automatically query showmount on all discovered hosts
                self._query_targets_worker()
            except Exception as e:
                self.log(f"Nmap error: {e}", level="ERROR")
            finally:
                self.is_busy = False
                self.refresh_ui_tables()

        threading.Thread(target=_worker, daemon=True).start()

    def scan_arpscan_async(self):
        if self.is_busy:
            return
        self.is_busy = True

        def _worker():
            try:
                dpg.set_value("status_text", "Running arp-scan & avahi-resolve...")
                results = self.mgr.scan_network_arpscan(progress_cb=self.log)
                hostnames = [r["host"] for r in results]
                added = self.append_target_hosts(hostnames)
                self.log(f"arp-scan & avahi-resolve complete. Found {len(results)} host(s) ({len(added)} new targets added).")

                # Automatically query showmount on all discovered hosts
                self._query_targets_worker()
            except Exception as e:
                self.log(f"arp-scan error: {e}", level="ERROR")
            finally:
                self.is_busy = False
                self.refresh_ui_tables()

        threading.Thread(target=_worker, daemon=True).start()

    def query_targets_async(self):
        if self.is_busy:
            return
        self.is_busy = True

        def _worker():
            try:
                self._query_targets_worker()
            finally:
                self.is_busy = False
                self.refresh_ui_tables()

        threading.Thread(target=_worker, daemon=True).start()

    def _query_targets_worker(self):
        hosts = self.get_current_target_hosts()
        if not hosts:
            self.log("Target hosts list is empty. Add hosts or run a scan first.", level="WARN")
            return

        self.log(f"Querying showmount exports on {len(hosts)} target host(s)...")
        dpg.set_value("status_text", f"Querying showmount on {len(hosts)} host(s)...")

        shares = self.mgr.query_multiple_hosts(hosts, progress_callback=lambda msg: self.log(msg))
        self.discovered_shares = shares
        self.log(f"Query complete. Found {len(shares)} total exported NFS share(s).")

    # -----------------------------------------------------------------------
    # Table Rendering
    # -----------------------------------------------------------------------
    def refresh_ui_tables(self):
        self.active_mounts = self.mgr.get_active_mounts()
        active_sources = {m.source: m.mount_point for m in self.active_mounts}

        # 1. Update Discovered Exports Table
        if dpg.does_item_exist("shares_table"):
            dpg.delete_item("shares_table", children_only=True)

            dpg.add_table_column(label="Status", width_fixed=True, init_width_or_weight=90, parent="shares_table")
            dpg.add_table_column(label="Host", width_fixed=True, init_width_or_weight=140, parent="shares_table")
            dpg.add_table_column(label="Remote Export Path", parent="shares_table")
            dpg.add_table_column(label="Allowed Clients", width_fixed=True, init_width_or_weight=150, parent="shares_table")
            dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=100, parent="shares_table")

            for share in self.discovered_shares:
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

        # 2. Update Active Mounts Table
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

    # -----------------------------------------------------------------------
    # Mount Modal Dialog
    # -----------------------------------------------------------------------
    def open_mount_modal(self, share):
        self.selected_share_for_mount = share
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

    # -----------------------------------------------------------------------
    # GUI Layout Construction
    # -----------------------------------------------------------------------
    def build_gui(self):
        dpg.create_context()
        self.setup_monkeytype_theme()

        # Detect initial default subnet
        detected_subnets = self.mgr.get_local_subnets()
        default_subnet = detected_subnets[0] if detected_subnets else "192.168.10.0/24"

        with dpg.window(tag="primary_window"):
            # Header Bar
            with dpg.group(horizontal=True):
                dpg.add_text("NFS MOUNT EXPLORER", color=(226, 183, 20))
                dpg.add_text("|", color=(100, 102, 105))
                dpg.add_text("Dynamic Discovery & Mount Manager", color=(100, 102, 105))
                dpg.add_spacer(width=20)
                dpg.add_text("Ready", tag="status_text", color=(209, 208, 197))

            dpg.add_separator()
            dpg.add_spacer(height=3)

            # ---------------------------------------------------------------
            # Discovery & Target Input Panel
            # ---------------------------------------------------------------
            with dpg.collapsing_header(label="Network Discovery & Target Hosts", default_open=True):
                with dpg.group(horizontal=True):
                    # Left Column: Automated Network Scanners
                    with dpg.child_window(width=420, height=185, border=True):
                        dpg.add_text("Automated LAN Scanners", color=(226, 183, 20))
                        dpg.add_spacer(height=3)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Target Subnet:")
                            dpg.add_input_text(tag="subnet_input", default_value=default_subnet, width=170)

                        with dpg.group(horizontal=True):
                            dpg.add_checkbox(tag="nmap_nfs_only_check", default_value=True)
                            dpg.add_text("Probe NFS Port 2049 directly (Fast)")

                        dpg.add_spacer(height=4)
                        with dpg.group(horizontal=True):
                            nmap_btn = dpg.add_button(
                                label="Scan LAN (Nmap)",
                                callback=lambda: self.scan_nmap_async()
                            )
                            dpg.bind_item_theme(nmap_btn, self.gold_btn_theme)

                            arp_btn = dpg.add_button(
                                label="Scan (arp-scan + avahi-resolve)",
                                callback=lambda: self.scan_arpscan_async()
                            )
                            dpg.bind_item_theme(arp_btn, self.gold_btn_theme)

                        dpg.add_spacer(height=6)
                        dpg.add_text("File Import:", color=(100, 102, 105))
                        with dpg.group(horizontal=True):
                            dpg.add_input_text(tag="hosts_file_path", default_value="/etc/hosts", width=200)
                            dpg.add_button(
                                label="Browse...",
                                callback=lambda: dpg.show_item("file_picker_hosts_id")
                            )
                            dpg.add_button(
                                label="Load File",
                                callback=lambda: self.load_hosts_from_file_cb()
                            )

                    # Right Column: Multiline User Input for Targets
                    with dpg.child_window(width=-1, height=185, border=True):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Candidate Hosts / IPs (Editable):", color=(226, 183, 20))
                            dpg.add_spacer(width=20)
                            dpg.add_button(
                                label="Clear",
                                callback=lambda: dpg.set_value("targets_text_input", "")
                            )

                        dpg.add_input_text(
                            tag="targets_text_input",
                            multiline=True,
                            width=-1,
                            height=100,
                            hint="Enter hostnames or IPs (one per line, comma, or space separated):\ne.g.\npi02.local\n192.168.10.150\npi03.local",
                            default_value=""
                        )

                        dpg.add_spacer(height=4)
                        with dpg.group(horizontal=True):
                            query_btn = dpg.add_button(
                                label="Query Showmount on Targets",
                                callback=lambda: self.query_targets_async()
                            )
                            dpg.bind_item_theme(query_btn, self.gold_btn_theme)

                            dpg.add_button(
                                label="Refresh Active Mounts",
                                callback=lambda: self.refresh_ui_tables()
                            )

            dpg.add_spacer(height=5)

            # ---------------------------------------------------------------
            # Tables: Discovered Exports & Active Mounts
            # ---------------------------------------------------------------
            with dpg.tab_bar():
                # Tab 1: Discovered NFS Exports
                with dpg.tab(label="Discovered NFS Exports"):
                    with dpg.child_window(height=230, border=True):
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
                            dpg.add_table_column(label="Host", width_fixed=True, init_width_or_weight=140)
                            dpg.add_table_column(label="Remote Export Path")
                            dpg.add_table_column(label="Allowed Clients", width_fixed=True, init_width_or_weight=150)
                            dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=100)

                # Tab 2: Active OS Mounts
                with dpg.tab(label="Active System Mounts"):
                    with dpg.child_window(height=230, border=True):
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

            dpg.add_spacer(height=3)

            # Activity Log Panel
            with dpg.collapsing_header(label="Execution & Activity Log", default_open=True):
                dpg.add_input_text(
                    tag="log_box",
                    multiline=True,
                    readonly=True,
                    width=-1,
                    height=110,
                    default_value="[System] NFS Explorer ready. Input target hosts, load a file, or click a network scan."
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
            width=520,
            height=310
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
                dpg.add_input_text(tag="modal_mount_point", width=380, default_value="/mnt/nfs_share")
                dpg.add_button(
                    label="Browse",
                    callback=lambda: dpg.show_item("file_picker_dir_id")
                )

            dpg.add_spacer(height=5)
            dpg.add_text("Mount Options:")
            dpg.add_input_text(tag="modal_options", width=-1, default_value="rw,sync,noatime,_netdev")

            dpg.add_spacer(height=5)
            dpg.add_text("Sudo Password (if required):")
            dpg.add_input_text(tag="modal_sudo_pwd", password=True, width=-1, hint="Leave empty if using polkit or passwordless sudo")

            dpg.add_text("", tag="modal_error_text", color=(202, 71, 84))
            dpg.add_spacer(height=8)

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

        # -------------------------------------------------------------------
        # File & Directory Pickers
        # -------------------------------------------------------------------
        # Directory Picker for Mount Point
        def _dir_selected_cb(sender, app_data):
            selected_path = app_data.get("file_path_name")
            if selected_path:
                dpg.set_value("modal_mount_point", selected_path)

        dpg.add_file_dialog(
            directory_selector=True,
            show=False,
            callback=_dir_selected_cb,
            tag="file_picker_dir_id",
            width=500,
            height=350
        )

        # File Picker for Hosts File
        def _hosts_file_selected_cb(sender, app_data):
            selected_path = app_data.get("file_path_name")
            if selected_path:
                dpg.set_value("hosts_file_path", selected_path)
                self.load_hosts_from_file_cb()

        dpg.add_file_dialog(
            directory_selector=False,
            show=False,
            callback=_hosts_file_selected_cb,
            tag="file_picker_hosts_id",
            width=500,
            height=350
        )

        # Viewport Initialization
        dpg.create_viewport(title="NFS Mount Explorer (Monkeytype Theme)", width=890, height=690)
        dpg.setup_dearpygui()
        dpg.set_primary_window("primary_window", True)
        dpg.show_viewport()

        # Initial Active Mounts Populate
        self.refresh_ui_tables()

        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    app = NFSGuiApp()
    app.build_gui()
