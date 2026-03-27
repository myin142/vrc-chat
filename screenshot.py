#!/usr/bin/env python3
"""
Wayland Screenshot Tool (Sway / wlroots)
=========================================
Select an application window by clicking on it, then capture a screenshot.

Requirements (system packages):
  - grim    : Wayland-native screenshot utility
  - slurp   : Wayland-native region / window selector
  - swaymsg : Sway IPC (ships with Sway)
    - wl-copy : Clipboard writer (from wl-clipboard)
  - jq      : JSON processor (used internally by swaymsg)

Usage:
  python screenshot.py                  # click a window → saves PNG
  python screenshot.py -o ~/my_shot.png # custom output path
  python screenshot.py --list           # list visible windows and exit
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result. Abort on failure."""
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"Error running {' '.join(cmd)}:", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return result


def check_dependencies() -> None:
    """Make sure the required system tools are installed."""
    missing = []
    for tool in ("grim", "slurp", "swaymsg", "wl-copy"):
        if not _which(tool):
            missing.append(tool)
    if missing:
        print(
            f"Missing required tools: {', '.join(missing)}\n"
            f"Install them with your package manager (e.g. pacman -S {' '.join(missing)})",
            file=sys.stderr,
        )
        sys.exit(1)


def _which(name: str) -> bool:
    return subprocess.run(
        ["which", name], capture_output=True, text=True
    ).returncode == 0


# ── sway window tree helpers ────────────────────────────────────────────────

def get_sway_tree() -> dict:
    """Fetch the full Sway window tree via IPC."""
    result = run(["swaymsg", "-t", "get_tree"])
    return json.loads(result.stdout)


def _collect_windows(node: dict) -> list[dict]:
    """
    Recursively walk the Sway tree and collect all visible leaf windows
    (actual application windows, not containers/workspaces).
    """
    windows: list[dict] = []

    # A "leaf" window has no further child nodes and has a valid rect
    is_leaf = node.get("type") in ("con", "floating_con") and not node.get("nodes") and not node.get("floating_nodes")
    is_visible = node.get("visible", False) or node.get("type") == "floating_con"
    rect = node.get("rect", {})
    has_size = rect.get("width", 0) > 0 and rect.get("height", 0) > 0

    if is_leaf and has_size:
        windows.append({
            "name": node.get("name", "unnamed"),
            "app_id": node.get("app_id") or node.get("window_properties", {}).get("class", "unknown"),
            "id": node.get("id"),
            "rect": rect,
            "focused": node.get("focused", False),
        })

    # Recurse into children
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        windows.extend(_collect_windows(child))

    return windows


def get_visible_windows() -> list[dict]:
    """Return a list of all visible application windows with their geometry."""
    tree = get_sway_tree()
    return _collect_windows(tree)


def format_geometry(rect: dict) -> str:
    """Format a rect dict as a 'WxH+X+Y' geometry string for grim."""
    return f"{rect['x']},{rect['y']} {rect['width']}x{rect['height']}"


# ── screenshot actions ───────────────────────────────────────────────────────

def select_window_with_slurp(windows: list[dict]) -> dict | None:
    """
    Pipe all window geometries into slurp so the user can click on a window
    to select it. Returns the matching window dict, or None.
    """
    if not windows:
        print("No visible windows found.", file=sys.stderr)
        return None

    # Build the slurp input: one line per window in "x,y wxh label" format
    slurp_input = "\n".join(
        f"{w['rect']['x']},{w['rect']['y']} {w['rect']['width']}x{w['rect']['height']} {w['app_id']}"
        for w in windows
    )

    result = subprocess.run(
        ["slurp"],
        input=slurp_input,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # User cancelled (Escape)
        return None

    chosen_geom = result.stdout.strip()  # e.g. "100,200 800x600"

    # Match back to a window
    for w in windows:
        geom = format_geometry(w["rect"])
        if geom == chosen_geom:
            return w

    # Fallback: return the raw geometry even if we can't match a window name
    # (can happen with sub-pixel rounding differences)
    parts = chosen_geom.replace(",", " ").replace("x", " ").split()
    if len(parts) == 4:
        return {
            "name": "selected region",
            "app_id": "unknown",
            "rect": {
                "x": int(parts[0]),
                "y": int(parts[1]),
                "width": int(parts[2]),
                "height": int(parts[3]),
            },
        }
    return None


def select_region_with_slurp() -> dict | None:
    """
    Let the user click and drag to select an arbitrary rectangular region
    of the screen. Returns a rect dict, or None if cancelled.
    """
    result = subprocess.run(
        ["slurp"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return None

    chosen = result.stdout.strip()  # e.g. "100,200 800x600"
    parts = chosen.replace(",", " ").replace("x", " ").split()
    if len(parts) == 4:
        return {
            "name": "selected region",
            "app_id": "region",
            "rect": {
                "x": int(parts[0]),
                "y": int(parts[1]),
                "width": int(parts[2]),
                "height": int(parts[3]),
            },
        }
    return None


def capture_window(rect: dict, output_path: str) -> str:
    """Use grim to capture a specific rectangular region and save to output_path."""
    geom = format_geometry(rect)
    run(["grim", "-g", geom, output_path])
    return output_path


def copy_image_to_clipboard(image_path: str) -> bool:
    """Copy a PNG image file into the Wayland clipboard using wl-copy."""
    try:
        with open(image_path, "rb") as image_file:
            result = subprocess.run(
                ["wl-copy", "--type", "image/png"],
                stdin=image_file,
                capture_output=True,
            )
    except OSError as exc:
        print(f"Warning: failed to copy screenshot to clipboard: {exc}", file=sys.stderr)
        return False

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        if stderr:
            print(f"Warning: failed to copy screenshot to clipboard: {stderr}", file=sys.stderr)
        else:
            print("Warning: failed to copy screenshot to clipboard.", file=sys.stderr)
        return False

    return True


def default_output_path() -> str:
    """Generate a timestamped filename in ~/Pictures/Screenshots/."""
    screenshots_dir = Path.home() / "Pictures" / "Screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return str(screenshots_dir / f"screenshot_{timestamp}.png")


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wayland window screenshot tool (Sway / wlroots)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: ~/Pictures/Screenshots/screenshot_<timestamp>.png)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all visible windows and exit",
    )
    parser.add_argument(
        "-r", "--region",
        action="store_true",
        help="Click and drag to select an arbitrary screen region",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    check_dependencies()

    windows = get_visible_windows()

    # ── list mode ────────────────────────────────────────────────────────
    if args.list:
        if not windows:
            print("No visible windows found.")
            return
        print(f"{'#':<4} {'App ID':<30} {'Geometry':<25} {'Title'}")
        print("-" * 90)
        for i, w in enumerate(windows, 1):
            geom = f"{w['rect']['width']}x{w['rect']['height']}+{w['rect']['x']}+{w['rect']['y']}"
            print(f"{i:<4} {w['app_id']:<30} {geom:<25} {w['name']}")
        return

    # ── region selection ─────────────────────────────────────────────────
    if args.region:
        print("Click and drag to select a region (press Escape to cancel)...")
        window = select_region_with_slurp()
        if window is None:
            print("Selection cancelled.")
            sys.exit(0)
    else:
        # ── interactive window selection ─────────────────────────────────
        print("Click on a window to capture it (press Escape to cancel)...")
        window = select_window_with_slurp(windows)
        if window is None:
            print("Selection cancelled.")
            sys.exit(0)

    output = args.output or default_output_path()
    output = os.path.expanduser(output)

    capture_window(window["rect"], output)
    copied = copy_image_to_clipboard(output)

    app_label = window.get("app_id", "unknown")
    title = window.get("name", "")
    print(f"✓ Captured [{app_label}] {title}")
    print(f"  → {output}")
    if copied:
        print("  → Copied to clipboard")


if __name__ == "__main__":
    main()
