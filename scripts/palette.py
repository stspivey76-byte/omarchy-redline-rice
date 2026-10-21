"""Color picker and deterministic recoloring of the existing theme/plugin text assets."""
import colorsys
from contextlib import ExitStack
import os
from pathlib import Path
import re
import shutil

COLORS = {"red": "#d51b36", "blue": "#1b62d5", "green": "#59d51b", "yellow": "#d5af1b", "pink": "#d51b94", "purple": "#891bd5"}
HEX = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b")
ANSI = re.compile(r"(38;2;)(\d+);(\d+);(\d+)")
RGB_LINE = re.compile(r"(?m)^(\w+=)(\d+),(\d+),(\d+)$")
PAYLOAD = ("VERSION", "install.sh", "scripts", "theme", "plugins", "hooks", "fastfetch", "shell.json", "shell.toml")


def recolor_rgb(rgb, color):
    _, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb))
    if saturation < 0.06:
        return tuple(rgb)  # Preserve neutral text, black, white and alpha.
    seed = COLORS[color].lstrip("#")
    hue = colorsys.rgb_to_hsv(*(int(seed[i:i + 2], 16) / 255 for i in (0, 2, 4)))[0]
    return tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, saturation, value))


def recolor_text(text, color):
    def hex_color(match):
        raw = match.group()[1:]
        alpha, raw = (raw[:2], raw[2:]) if len(raw) == 8 else ("", raw)
        rgb = recolor_rgb(tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4)), color)
        return "#" + alpha + "".join(f"{channel:02x}" for channel in rgb)
    text = HEX.sub(hex_color, text)
    text = ANSI.sub(lambda m: m[1] + ";".join(map(str, recolor_rgb(tuple(map(int, m.group(2, 3, 4))), color))), text)
    return RGB_LINE.sub(lambda m: m[1] + ",".join(map(str, recolor_rgb(tuple(map(int, m.group(2, 3, 4))), color))), text)


def stage(source, destination, color):
    destination.mkdir(parents=True, exist_ok=True)
    for name in PAYLOAD:
        origin = source / name
        if origin.is_dir():
            shutil.copytree(origin, destination / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(origin, destination / name)
    for path in destination.rglob("*"):
        if path.is_file() and path.suffix in (".toml", ".qml", ".css", ".colors", ".jsonc", ".txt", ".lua"):
            text = recolor_text(path.read_text(), color)
            if color in ("green", "yellow") and path.suffix == ".css":
                text = text.replace("@define-color accent_fg_color #ffffff;", "@define-color accent_fg_color #080406;").replace("--accent-fg-color: #ffffff;", "--accent-fg-color: #080406;")
                text = text.replace("@define-color theme_selected_fg_color #ffffff;", "@define-color theme_selected_fg_color #080406;")
            if color in ("green", "yellow") and path.suffix == ".colors":
                text = re.sub(r"(\[Colors:Selection\][\s\S]*?ForegroundNormal=)[^\n]*", r"\g<1>8,4,6", text)
            path.write_text(text)
    # Stable selected filename keeps existing theme hooks/background paths compatible.
    wallpaper = "tux-crimson-eclipse.png" if color == "red" else f"tux-{color}-eclipse.png"
    shutil.copy2(source / "theme/backgrounds" / wallpaper, destination / "theme/backgrounds/tux-crimson-eclipse.png")
    return destination


def picker(default, desktop, terminal):
    seed = COLORS[default]
    channels = tuple(int(seed[i:i + 2], 16) for i in (1, 3, 5))
    accent = "\033[38;2;" + ";".join(map(str, channels)) + "m"
    reset, bright, dim = "\033[0m", "\033[1;97m", "\033[38;2;145;145;155m"
    tux = [r"      .--.      ", r"     |o_o |     ", r"     |:_/ |     ",
           r"    //   \ \    ", r"   (|     | )   ", r"  /'\_   _/`\   ", r"  \___)=(___/   "]
    eclipse = ["         ·         .-========-.     ✦", "   ✦             .'           `.   ░",
               "                /               \\ ▒", "        ·      |                 |▓█",
               "                \\               / ▓", "    ✦            `.           .'  ▒",
               "             ·     `-=======-'   ░"]
    terminal.write("\n" + accent + "  ╭" + "─" * 62 + "╮\n" + reset)
    terminal.write(accent + "  │" + bright + "R E D L I N E   ·   D E S K T O P".center(62) + accent + "│\n" + reset)
    terminal.write(accent + "  ╰" + "─" * 62 + "╯\n\n" + reset)
    for penguin, moon in zip(tux, eclipse):
        terminal.write("   " + bright + penguin + accent + moon + reset + "\n")
    terminal.write(dim + "\n           Tux. Eclipse. Six colors. Your atmosphere.\n" + reset)
    terminal.write(f"  {dim}DESKTOP{reset}  {bright}{desktop}{reset}\n")
    terminal.write(f"  {dim}MATCHES{reset}  wallpaper · taskbar · GTK · Fastfetch\n\n")
    entries = []
    for index, (name, rgb) in enumerate(COLORS.items(), 1):
        channels = tuple(int(rgb[i:i + 2], 16) for i in (1, 3, 5))
        swatch = "\033[38;2;" + ";".join(map(str, channels)) + "m●\033[0m"
        selected = name == default
        entries.append(f"{'›' if selected else ' '} {index}  {swatch}  {bright if selected else ''}{name.title():<8}{reset}" + (accent + "CURRENT" + reset if selected else "       "))
    for index in range(0, len(entries), 2):
        terminal.write("  " + entries[index] + "      " + entries[index + 1] + "\n")
    terminal.write(dim + "  Settings backed up · Updates remember your color\n" + reset)
    while True:
        terminal.write(f"\n  Choose 1–6 or a color name [Enter: {default}, q: cancel]: ")
        terminal.flush()
        line = terminal.readline()
        if not line:
            raise SystemExit("Installation cancelled (terminal closed).")
        answer = line.strip().lower()
        if answer in ("q", "quit", "cancel"):
            raise SystemExit("Installation cancelled.")
        if not answer:
            return default
        if answer in COLORS:
            return answer
        if answer in tuple(map(str, range(1, 7))):
            return tuple(COLORS)[int(answer) - 1]
        terminal.write("  Please choose red, blue, green, yellow, pink, or purple.\n")


def choose_color(default, desktop):
    if os.environ.get("REDLINE_UPDATER_RUNNING"):
        saved = os.environ.get("REDLINE_SELECTED_COLOR", default)
        return saved if saved in COLORS else default
    # curl | bash consumes stdin, so use the controlling terminal directly.
    with ExitStack() as stack:
        try:
            reader = stack.enter_context(open("/dev/tty", "r"))
            writer = stack.enter_context(open("/dev/tty", "w", buffering=1))
        except OSError:
            raise SystemExit("Open a terminal and run the installer to choose your color from the menu.")
        class Terminal:
            readline = reader.readline
            write = writer.write
            flush = writer.flush
        return picker(default, desktop, Terminal())
