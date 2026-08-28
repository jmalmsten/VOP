# modules/leds.py
#
# VOP onboard-LED blanker — best-effort control of the Pi's red PWR and green
# ACT status LEDs, so they can be switched OFF for the duration of a camera
# exposure and back ON afterwards.
#
# ---------------------------------------------------------------------------
# WHY THIS EXISTS
#   The VOP lives in a light-tight cabinet with the HQ camera ~1.18m above the
#   projection monitor, and the Pi's onboard LEDs sit right next to the lens.
#   The red PWR LED is a steady stray source; the green ACT LED is worse during
#   a job (historically it strobes on every disk write). Either one fogs a long
#   exposure. The boot-time service (CaliTools/LedControl/setup_led_control.sh)
#   already: (a) detaches both LEDs from their kernel triggers so they stop
#   blinking on their own, (b) leaves them ON as a normal "powered up" light,
#   and (c) hands the VOP user write access to each LED's 'brightness' file via
#   the 'gpio' group. This module is the RUNTIME half: it writes 0 to blank and
#   1 to restore, around each exposure, with NO sudo.
#
# ---------------------------------------------------------------------------
# DESIGN RULES (same spirit as notifier.py's "cannot throw" writer)
#   * BEST-EFFORT, NEVER THROWS. Blanking a status LED is a nicety, never
#     load-bearing. Every function swallows ALL exceptions. A missing sysfs
#     node, a permission error (boot service not installed / user not in the
#     'gpio' group), a read-only file — none of it may ever bubble up and abort
#     an exposure that could be hours deep. Worst case: the LED simply stays
#     lit, exactly as if this module did nothing.
#   * STDLIB ONLY. Plain file writes to /sys/class/leds/*/brightness. No deps.
#   * RESOLVE ONCE. The engine imports this module a single time (persistent
#     daemon), so we discover the LED node paths at import and cache them. LED
#     nodes do not come and go at runtime, so there is nothing to re-scan.
#
# ---------------------------------------------------------------------------
# NAMING NOTE
#   Node names must match what setup_led_control.sh configured, newest naming
#   first. Current Pi OS: red = "PWR", green = "ACT". Older images: red =
#   "led1", green = "led0". We keep both so a reflash onto an older image still
#   works. If you ever want to leave one LED as a live indicator, delete its
#   candidates from the list below (and from the setup script).
# ---------------------------------------------------------------------------
#
###########################################################################
#
#                                   VOP
#                       Copyright (C) 2025  jmalmsten
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as
#     published by the Free Software Foundation, either version 3 of the
#     License, or (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with this program.  If not, see
#     <http://www.gnu.org/licenses/>.
#
#     Source code for this application can be found at
#     https://github.com/jmalmsten/VOP
#
###########################################################################

import os

# Where the kernel exposes each LED. Same base the setup script uses.
_LED_BASE = "/sys/class/leds"

# Candidate node names per physical LED, newest naming first. This mirrors
# RED_CANDIDATES / GREEN_CANDIDATES in setup_led_control.sh — keep them in sync.
_LED_CANDIDATES = [
    ("PWR", "led1"),   # red power LED
    ("ACT", "led0"),   # green activity LED
]

# Brightness value used to turn an LED back ON. The boot service also uses 1
# (any nonzero lights the LED); restoring to 1 reproduces the exact "idle"
# state the service leaves at boot, so ON after an exposure looks identical to
# ON before the job started.
_ON_VALUE = 1


def _resolve_brightness_files():
    """
    Find the writable 'brightness' file for each physical LED, once, at import.

    Returns a list of filesystem paths (strings). For each LED we take the
    first candidate node that actually exists on this board; missing LEDs are
    simply skipped. Never raises — a scan problem just yields fewer paths.
    """
    paths = []
    for candidates in _LED_CANDIDATES:
        for name in candidates:
            bfile = os.path.join(_LED_BASE, name, "brightness")
            # os.path.exists on a sysfs node is a cheap, safe stat. We do not
            # check writability here: whether we CAN write is decided at write
            # time and swallowed, so an un-writable node still gets recorded
            # and simply fails its write later (harmlessly).
            if os.path.exists(bfile):
                paths.append(bfile)
                break  # first existing candidate wins; don't double-add an LED
    return paths


# Resolved at import. If empty (no LED nodes, e.g. running off-Pi during a
# desktop diagnostic), every function below becomes a silent no-op.
_BRIGHTNESS_FILES = _resolve_brightness_files()


def _write_all(value):
    """
    Write the same integer 'value' to every resolved brightness file.

    Best-effort and per-node isolated: one LED failing (missing, permission)
    must not stop us writing the other. Swallows everything and returns the
    count of successful writes (handy for the diagnostic below; the engine
    ignores it).
    """
    written = 0
    for bfile in _BRIGHTNESS_FILES:
        try:
            # Open per call rather than holding a handle: sysfs brightness is a
            # tiny attribute file, opening it is effectively free, and not
            # holding descriptors keeps this module completely stateless.
            with open(bfile, "w") as f:
                f.write(str(value))
            written += 1
        except Exception:
            # Node vanished, not group-writable (boot service not installed or
            # user not in 'gpio'), or read-only — none of that is worth failing
            # an exposure over. Silent by design; add a print() here temporarily
            # if you ever need to see WHY a write didn't land.
            pass
    return written


def off():
    """Blank ALL onboard LEDs (write 0). Call just before a camera exposure."""
    return _write_all(0)


def on():
    """Restore ALL onboard LEDs (write 1). Call just after the exposure ends."""
    return _write_all(_ON_VALUE)


# --- Standalone diagnostic --------------------------------------------------
# Run directly on the Pi to sanity-check wiring WITHOUT the engine:
#     python3 modules/leds.py
# It reports which nodes were found, then blinks them off/on a few times so you
# can confirm the runtime path (group write access, correct nodes) actually
# works before trusting it inside a job. Import side effects are nil; this only
# runs under __main__.
if __name__ == "__main__":
    import time
    print(f"[leds] LED base: {_LED_BASE}")
    if not _BRIGHTNESS_FILES:
        print("[leds] No LED brightness nodes found. Are you on the Pi? "
              "Did the boot service run? Nothing to control — no-op mode.")
    else:
        print("[leds] Controlling brightness nodes:")
        for p in _BRIGHTNESS_FILES:
            print(f"         {p}")
        print("[leds] Blinking 3x (off ~0.5s / on ~0.5s). Watch the board...")
        for i in range(3):
            n = off()
            print(f"         cycle {i + 1}: off  ({n} node(s) written)")
            time.sleep(0.5)
            n = on()
            print(f"         cycle {i + 1}: on   ({n} node(s) written)")
            time.sleep(0.5)
        print("[leds] Done. If nothing visibly blinked but writes reported >0, "
              "the LED trigger may still be attached — check the boot service.")