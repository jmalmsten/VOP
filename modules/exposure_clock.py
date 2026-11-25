"""
exposure_clock.py - frame scheduler for the HDMI "image phase" of an exposure.

THE PROBLEM THIS SOLVES
-----------------------
The camera's shutter is open for a fixed time. Whatever the monitor is
showing during that time is what gets exposed, so the *length of time the
image is on the panel* is the exposure. Anything that makes that length vary
from one frame to the next shows up as flicker in the finished film.

Rendering one composite frame on the Pi 4 takes 3-5 monitor refreshes, so a
loop of "render, flip, render, flip ..." cannot be used to count time. This
module instead treats the monitor as a clock:

  * The monitor's vertical blank (vblank) happens at a fixed rate (60 Hz).
    Every picture change we make lands on a vblank. We call these slots.
  * An exposure of 0.75 s is exactly S = round(0.75 / refresh) slots. Not
    "about" S: the final swap to black is scheduled against an absolute
    deadline, so slow renders can never stretch the exposure.
  * The S slots are split into K groups. Each group is one rendered frame,
    held for a few slots. Frames are rendered into the back buffer while the
    previous group is on screen, then swapped in just before its vblank.
  * If an exposure is static (nothing moves), K = 1: render once, hold S slots.

This file has NO pygame / OpenGL in it on purpose: the engine hands in
callbacks, so the timing logic can be tested on any machine with a fake
display, without a Pi or a monitor.
"""

import math
import time

# ------------------------------------------------------------------
# TUNABLES (all are fractions of one refresh period unless stated)
# ------------------------------------------------------------------
# A swap must be *requested* a while before the vblank it is aimed at. Three
# things eat into that lead: the swap call itself takes ~1-3 ms before the
# page-flip request reaches the display hardware, the hardware needs the
# request ~1-2 ms before the vblank, and our own timer can overshoot. The
# ideal request time is the middle of the slot, so the lead is about
# half a refresh PLUS the swap cost.
#
# The two edges of the image phase (first image swap, final swap to black)
# decide the exposure length, so they get the safest, most centred lead.
# Swaps between groups only move time between two neighbouring groups, so
# they use a shorter lead (leaves more time to render the next frame).
LEAD_EDGE = 0.75
LEAD_MID  = 0.55

# Never aim a swap at a vblank that is closer than this to "now" (the swap
# call itself takes a couple of ms, then the hardware needs ~1-2 ms more).
MIN_SWAP_LEAD = 0.30

# The FIRST image swap decides when the exposure starts. If our timer woke us
# up so late that fewer than this many ms remain before the planned vblank,
# nobody can say whether the swap makes it, so we deliberately aim at the NEXT
# vblank instead (one extra black slot, harmless) and the start is certain.
SAFE_MARGIN_MS = 8.0

# Group size is chosen from the measured render time:
#   group_ms >= render_ms * RENDER_SAFETY + RENDER_PAD_MS + lead
RENDER_SAFETY = 1.08
RENDER_PAD_MS = 1.0

# Renders done before the exposure. The first one after idle is usually slower
# (GPU clock ramp, cache warm-up) so it is thrown away; the slowest of the
# others sets the group size. (A static exposure renders only once.)
WARM_RENDERS = 3


# ------------------------------------------------------------------
# CLOCK
# ------------------------------------------------------------------
class RealClock:
    """Wall clock with an accurate 'wait until' (sleep, then spin)."""

    def now(self):
        return time.perf_counter()

    def wait_until(self, t, spin_s=0.002):
        # time.sleep() can overshoot by a millisecond or more on a busy Pi,
        # so sleep until ~2 ms before the target and burn the rest in a
        # tight loop. The spin is at most 2 ms per wait, so CPU cost is nil.
        while True:
            remaining = t - time.perf_counter()
            if remaining <= 0.0:
                return
            if remaining > spin_s:
                time.sleep(remaining - spin_s)


# ------------------------------------------------------------------
# VBLANK GRID
# ------------------------------------------------------------------
class VblankGrid:
    """Predicts vblank times: vblank(n) = t0 + n * period (seconds)."""

    def __init__(self, t0, period):
        self.t0 = t0
        self.period = period

    def time(self, n):
        return self.t0 + n * self.period

    def next_index(self, t):
        """Index of the first vblank at or after time t."""
        return int(math.ceil((t - self.t0) / self.period - 1e-9))


def fit_vblank_grid(stamps, period_hint, skip=3, outlier_s=0.002,
                    fit_period=False):
    """
    Fit the vblank grid from the return times of back-to-back black flips.

    stamps      : perf_counter() taken right after each black flip returned.
    period_hint : the refresh period in SECONDS (boot measurement).
    skip        : ignore the first few flips (the first one after idle can
                  return early because nothing was pending).
    outlier_s   : a stamp further than this from the fitted line is dropped.
    fit_period  : False -> the period is trusted and only the PHASE is
                  fitted (used before every exposure; needs few flips).
                  True  -> period and phase are both fitted by least squares
                  (used once at boot over ~180 flips, which pins the period
                  down far better than 30 flips could).

    Returns (VblankGrid, spread_ms, points_used) or None if the stamps do
    not look like a vsync-locked sequence (the caller then falls back).
    """
    pts = stamps[skip:]
    if len(pts) < 8:
        return None

    # Give every stamp the integer slot number it belongs to. Count slots
    # from one stamp to the NEXT (a flip that took two refreshes gets +2,
    # not +1). Counting from the first stamp instead would let a tiny error
    # in period_hint pile up over a long run and eventually miscount.
    idx = [0]
    for prev, cur in zip(pts, pts[1:]):
        idx.append(idx[-1] + max(1, int(round((cur - prev) / period_hint))))
    pairs = list(zip(idx, pts))

    a = b = None
    for _ in range(3):  # fit, drop outliers, refit
        n = float(len(pairs))
        if n < 8:
            return None
        if fit_period:
            sx = sum(i for i, _ in pairs)
            sy = sum(t for _, t in pairs)
            sxx = sum(i * i for i, _ in pairs)
            sxy = sum(i * t for i, t in pairs)
            den = n * sxx - sx * sx
            if den == 0:
                return None
            b = (n * sxy - sx * sy) / den      # period (s per slot)
            a = (sy - b * sx) / n              # time of slot index 0
        else:
            b = period_hint
            offs = sorted(t - i * b for i, t in pairs)
            med = offs[len(offs) // 2]         # median is outlier-proof
            close = [o for o in offs if abs(o - med) <= outlier_s]
            a = sum(close) / len(close)
        kept = [(i, t) for i, t in pairs if abs(t - (a + b * i)) <= outlier_s]
        if len(kept) == len(pairs):
            break
        pairs = kept

    if fit_period and abs(b - period_hint) > 0.01 * period_hint:
        return None  # more than 1% off the first estimate: don't trust it

    spread = max(abs(t - (a + b * i)) for i, t in pairs)
    return VblankGrid(a, b), spread * 1000.0, len(pairs)


def grid_residual_ms(grid, stamps):
    """
    Median distance (ms, wrapped to +-half a period) between flip-return
    stamps and the predicted vblank grid. Used AFTER an exposure as a check
    that the prediction held for the whole exposure: ~0 means yes.
    """
    if not stamps:
        return 0.0
    res = []
    for t in stamps:
        x = (t - grid.t0) / grid.period
        res.append((x - round(x)) * grid.period * 1000.0)
    res.sort()
    return res[len(res) // 2]


# ------------------------------------------------------------------
# PLANNING
# ------------------------------------------------------------------
def slots_for(exposure_ms, refresh_ms):
    """Whole refresh slots for an exposure (at least 1)."""
    return max(1, int(round(exposure_ms / refresh_ms)))


def choose_groups(total_slots, render_ms, refresh_ms):
    """
    How many rendered frames (groups) fit in the exposure.
    Returns (K, min_group_slots). Every group gets >= min_group_slots, so the
    next frame always has time to render while the current one is shown.
    """
    min_g = int(math.ceil((render_ms * RENDER_SAFETY + RENDER_PAD_MS) / refresh_ms
                          + LEAD_MID))
    min_g = max(1, min_g)
    return max(1, total_slots // min_g), min_g


def split_slots(total_slots, groups):
    """
    Split total_slots into `groups` sizes that differ by at most 1, with the
    larger ones spread evenly (so the time-average of the smear stays centred).
    """
    groups = max(1, min(groups, total_slots))
    base, extra = divmod(total_slots, groups)
    sizes = [base] * groups
    for j in range(extra):
        sizes[int((j + 0.5) * groups / extra)] += 1
    return sizes


def smear_positions(groups):
    """
    t_norm for each group: 0.0 .. 1.0 inclusive, so the first group shows the
    start pose and the last group the end pose (same convention as before).
    One group only: sample the middle of the smear.
    """
    if groups <= 1:
        return [0.5]
    return [k / (groups - 1.0) for k in range(groups)]


# ------------------------------------------------------------------
# THE IMAGE PHASE
# ------------------------------------------------------------------
def run_image_phase(clk, grid, total_slots, static, last_flip_ret,
                    render, swap, render_black, pump):
    """
    Show the exposure on the panel for exactly total_slots refreshes.

    Call this right after the black pre-roll. When it returns, the swap to
    black has been issued (it becomes visible at the planned vblank); the
    caller carries on with the black tail.

    Callbacks (all supplied by the engine):
      render(t_norm) : draw one composite frame into the BACK buffer and wait
                       for the GPU (ctx.finish()). Does NOT flip.
      swap()         : pygame.display.flip()
      render_black() : draw a black frame into the back buffer (no flip).
      pump()         : pygame.event.pump()

    Returns a dict with everything the audit log needs.
    """
    R = grid.period
    refresh_ms = R * 1000.0

    # ---- 1. Render frame 0 (also tells us how long a render takes) ----
    pump()
    times = []
    for _ in range(1 if static else WARM_RENDERS):
        t_a = clk.now()
        render(0.0)
        times.append((clk.now() - t_a) * 1000.0)
    render_ms = max(times[1:]) if len(times) > 1 else times[0]

    # ---- 2. Plan: how many groups, how long each ----
    if static:
        groups, min_g = 1, total_slots
    else:
        groups, min_g = choose_groups(total_slots, render_ms, refresh_ms)
    sizes = split_slots(total_slots, groups)
    groups = len(sizes)
    t_norms = smear_positions(groups)
    if groups == 1 and not static:
        # Exposure too short to show two different frames: show the middle
        # of the smear instead of its start. (Costs one more render.)
        render(t_norms[0])
    starts = [sum(sizes[:k]) for k in range(groups)]  # first slot of each group

    # ---- 3. Pick the vblank where the image first appears ----
    # The swap must not be requested before the last black flip has finished
    # (it can take one extra refresh to complete), and not before frame 0 is
    # rendered. Then round UP to the next vblank on the grid.
    earliest = max(clk.now(), last_flip_ret + 1.05 * R)
    n0 = int(math.ceil((earliest + LEAD_EDGE * R - grid.t0) / R - 1e-9))
    base = n0   # vblank index of slot 0; corrected below if the swap lands late

    def planned_call_time(k):
        lead = LEAD_EDGE if k == 0 else LEAD_MID
        return grid.time(base + starts[k]) - lead * R

    # ---- 4. Show the groups ----
    dropped = late = late_slots = 0
    first_call = None
    first_margin_ms = None
    flip_blocks = None
    for k in range(groups):
        if k > 0:
            pump()
            render(t_norms[k])

        t_plan = planned_call_time(k)
        now = clk.now()
        if k == 0:
            # Wait for the planned moment. If the timer woke us up too late
            # to be sure of making that vblank, aim at the next one instead.
            slipped = 0
            while True:
                clk.wait_until(planned_call_time(0))
                margin_ms = (grid.time(base) - clk.now()) * 1000.0
                if margin_ms >= SAFE_MARGIN_MS or slipped >= 3:
                    break
                base += 1
                slipped += 1
        elif now > t_plan:
            # Late. Find the first vblank we can still make.
            n_avail = grid.next_index(now + MIN_SWAP_LEAD * R)
            slot_avail = n_avail - base
            next_start = starts[k + 1] if k + 1 < groups else total_slots
            if slot_avail >= next_start:
                dropped += 1          # no room left: keep the old frame up
                continue
            late += 1
            late_slots += max(0, slot_avail - starts[k])
        else:
            clk.wait_until(t_plan)

        t_call = clk.now()
        swap()
        if k == 0:
            t_ret = clk.now()
            first_call = t_call
            first_margin_ms = (grid.time(base) - t_call) * 1000.0
            # If flip() blocked until its own vblank (double-buffered SDL),
            # its return time IS the vblank: read the real first slot from
            # it. Otherwise (SDL's default) trust the plan, which the
            # slip rule above made safe.
            flip_blocks = (t_ret - t_call) > 0.25 * R
            if flip_blocks:
                base = int(round((t_ret - grid.t0) / R))
            # Every later deadline is counted from the REAL first slot, so
            # a late start can never shorten the exposure.

    # ---- 5. The deadline: swap to black at an absolute vblank ----
    # Black is prepared early (it is one clear + one quad) and then we wait
    # for the exact moment, no matter how the renders went.
    pump()
    render_black()
    t_plan_f = grid.time(base + total_slots) - LEAD_EDGE * R
    now = clk.now()
    final_late = now > t_plan_f
    if not final_late:
        clk.wait_until(t_plan_f)
    t_call_f = clk.now()
    swap()
    t_ret_f = clk.now()
    final_block_ms = (t_ret_f - t_call_f) * 1000.0
    # With a blocking flip we can verify where the black really landed.
    final_slot_err = None
    if (t_ret_f - t_call_f) > 0.25 * R:
        final_slot_err = int(round((t_ret_f - grid.t0) / R)) - (base + total_slots)

    return {
        'slots': total_slots,
        'groups': groups,
        'sizes': sizes,
        'min_group_slots': min_g,
        'render_ms': render_ms,
        'dropped': dropped,
        'late': late,
        'late_slots': late_slots,
        'final_late': final_late,
        'first_vblank_index': base,
        'first_shift': base - n0,
        'flip_blocks': flip_blocks,
        'first_call': first_call,
        'first_margin_ms': first_margin_ms,
        'final_call': t_call_f,
        'final_margin_ms': (grid.time(base + total_slots) - t_call_f) * 1000.0,
        'final_block_ms': final_block_ms,
        'final_slot_err': final_slot_err,
        'span_ms': (t_call_f - first_call) * 1000.0,
        'planned_ms': total_slots * refresh_ms,
    }