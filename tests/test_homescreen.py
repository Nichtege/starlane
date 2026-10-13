"""The homescreen: the pure model (grid, zones, pages, placement) under Node, and the contract of its CSS and script (static).

The page itself is not driven here (no browser in the test suite): everything that can be decided without a DOM lives in the "homescreen
model" block of the script, which is cut out of dashboard.html and run as it is.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import JS_I18N

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
SCRIPT = re.search(r"<script>\n(.*?)</script>", HTML, re.S).group(1)

MODEL = SCRIPT[SCRIPT.index("// ---- homescreen model"): SCRIPT.index("// ---- end of the homescreen model")]
WIDGETS = SCRIPT[SCRIPT.index("const WIDGETS = ["): SCRIPT.index("const TodayView = {")]
VIEW = SCRIPT[SCRIPT.index("// ---- homescreen model"): SCRIPT.index("function stageTitle()")]
FIT_SRC = SCRIPT[SCRIPT.index("const WIDGET_FIT = {"): SCRIPT.index("function widgetEl(id) {")]   # the table and fitTile()


def _between(start: str, end: str) -> str:
    i = SCRIPT.index(start)
    return SCRIPT[i: SCRIPT.index(end, i)]


BASE_TILES = _between("  baseTiles(m) {", "  // Draw the tiles in their places.")
FLOW_ORDER = _between("  flowOrder() {", "  // Up / down in the flow layout")


def _blocks(css: str, opener: str):
    """The text inside every block that starts with `opener` (balanced braces)."""
    pos = 0
    while True:
        i = css.find(opener, pos)
        if i < 0:
            return
        j = css.index("{", i)
        depth = 0
        for k in range(j, len(css)):
            depth += css[k] == "{"
            depth -= css[k] == "}"
            if depth == 0:
                yield css[j + 1: k]
                pos = k
                break
        else:
            raise AssertionError("unbalanced block: " + opener)


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class HomescreenModelTests(unittest.TestCase):
    def _run(self, body: str):
        stubs = "".join(f"const {n} = () => null;\n" for n in sorted(set(re.findall(r"build: (\w+)", WIDGETS))))
        src = JS_I18N + f"""
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const STORE = {{}};
const store = {{ get(k) {{ return Object.prototype.hasOwnProperty.call(STORE, k) ? STORE[k] : null; }}, set(k, v) {{ STORE[k] = v; }} }};
{stubs}
{MODEL}
{WIDGETS}
const TV = {{ layout: null, tiles: [],
{BASE_TILES}
{FLOW_ORDER}
}};
// a small deterministic generator, so that a failing case can be reproduced
let seed = 12345;
const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const ri = (a, b) => a + Math.floor(rnd() * (b - a + 1));
const bad = (list, C, R) => {{
  const out = [];
  list.forEach((t, i) => {{
    const l = hsLeft(t, C);
    if (t.p < 0 || l < 0 || l + t.w > C || t.y < 0 || t.y + t.h > R || t.w < 1 || t.h < 1) out.push('bounds:' + t.id);
    list.forEach((q, j) => {{ if (j > i && hsHit(t, q, C)) out.push('overlap:' + t.id + '/' + q.id); }});
  }});
  return out;
}};
const byId = list => Object.fromEntries(list.map(t => [t.id, t]));
{body}
"""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # ---- the grid
    def test_wide_threshold(self):
        out = self._run("console.log(JSON.stringify([hsWide(1180, 620), hsWide(1179, 900), hsWide(1600, 619), hsWide(390, 844)]));")
        self.assertEqual(out, [True, False, False, False])

    def test_grid_covers_the_screen_and_leaves_room_for_the_galaxy(self):
        out = self._run("""
const rows = [];
for (const [W, H] of [[1180, 620], [1280, 720], [1366, 768], [1440, 800], [1536, 730], [1920, 1080], [2560, 1440], [3840, 2160]]) {
  const m = hsMetrics(W, H);
  rows.push({ W, H, C: m.C, R: m.R, Z: m.Z, px: m.px, py: m.py,
    right: W - (HS_PAD + m.C * m.px - HS_GAP), bottom: H - (HS_PAD + m.R * m.py - HS_GAP), free: W - 2 * (HS_PAD + m.Z * m.px) });
}
console.log(JSON.stringify(rows));
""")
        for r in out:
            tag = f"{r['W']}x{r['H']}"
            self.assertAlmostEqual(r["right"], 16, places=6, msg=tag)    # the last column ends one pad from the right edge
            self.assertAlmostEqual(r["bottom"], 56, places=6, msg=tag)   # ... and the last row above the dock
            self.assertTrue(8 <= r["C"] <= 40 and 4 <= r["R"] <= 24 and 2 <= r["Z"] <= 8, tag)
            self.assertTrue(56 <= r["px"] <= 100 and 56 <= r["py"] <= 100, tag)   # cells stay finger sized and never huge
            self.assertGreaterEqual(r["free"], 500, tag)                  # the galaxy keeps its room between the two zones

    def test_tiles_sit_on_the_edges_and_keep_the_gap(self):
        out = self._run("""
const W = 1440, H = 800, m = hsMetrics(W, H);
const l = hsBox({ a: 'l', x: 0, y: 0, w: 3, h: 2 }, m), n = hsBox({ a: 'l', x: 3, y: 0, w: 3, h: 2 }, m);
const r = hsBox({ a: 'r', x: 0, y: 0, w: 6, h: 2 }, m), under = hsBox({ a: 'l', x: 0, y: 2, w: 3, h: 2 }, m);
console.log(JSON.stringify({ left: l.left, gapX: n.left - (l.left + l.width), rightEdge: W - (r.left + r.width), gapY: under.top - (l.top + l.height), top: l.top }));
""")
        self.assertAlmostEqual(out["left"], 16, places=6)
        self.assertAlmostEqual(out["gapX"], 16, places=6)
        self.assertAlmostEqual(out["gapY"], 16, places=6)
        self.assertAlmostEqual(out["rightEdge"], 16, places=6)
        self.assertAlmostEqual(out["top"], 16, places=6)

    def test_anchor_keeps_a_tile_on_its_side_when_the_window_changes(self):
        out = self._run("""
const t = hsMake('a', 0, 0, 1, 6, 4, 21);          // at the left edge of a 21 column screen
const u = hsMake('b', 0, 15, 1, 6, 4, 21);         // at the right edge
const wide = [hsLeft(t, 21), hsLeft(u, 21)], narrow = [hsLeft(t, 17), hsLeft(u, 17)];
console.log(JSON.stringify({ a: [t.a, t.x], b: [u.a, u.x], wide, narrow }));
""")
        self.assertEqual(out["a"], ["l", 0])
        self.assertEqual(out["b"], ["r", 0])             # counted from the right edge: 21 - 15 - 6
        self.assertEqual(out["wide"], [0, 15])
        self.assertEqual(out["narrow"], [0, 11])         # on a 17 column screen it is still at the right edge

    def test_widths_scale_with_the_zone_and_never_drop_below_two(self):
        out = self._run("""
console.log(JSON.stringify([hsWidth(6, 6), hsWidth(3, 6), hsWidth(6, 3), hsWidth(3, 3), hsWidth(6, 2), hsWidth(6, 8), hsWidth(1, 6), hsWidth(4, 4)]));
""")
        self.assertEqual(out, [6, 3, 3, 2, 2, 6, 2, 2])

    # ---- no overlap, ever
    def test_resolve_is_overlap_free_deterministic_and_idempotent(self):
        out = self._run("""
const res = { cases: 0, bad: [], notIdempotent: 0, orderDependent: 0, pinMoved: 0, lost: 0 };
for (const [C, R] of [[17, 8], [21, 10], [30, 12], [8, 4]]) {
  for (let n = 0; n < 30; n++) {
    const list = [], count = ri(2, 40);
    for (let i = 0; i < count; i++) list.push({ id: 't' + i, p: ri(0, 2), a: rnd() < 0.5 ? 'l' : 'r', x: ri(0, C), y: ri(0, R), w: ri(1, 9), h: ri(1, 9) });
    const pin = rnd() < 0.5 ? list[ri(0, list.length - 1)].id : undefined;
    const r = hsResolve(list, C, R, pin);
    res.cases++;
    const b = bad(r, C, R);
    if (b.length) res.bad.push(C + 'x' + R + ' #' + n + ': ' + b.slice(0, 3).join(' '));
    if (r.length !== list.length || new Set(r.map(t => t.id)).size !== list.length) res.lost++;
    if (JSON.stringify(hsResolve(r, C, R, pin)) !== JSON.stringify(r)) res.notIdempotent++;   // running it again changes nothing
    const norm = l => JSON.stringify(l.slice().sort((a, b) => (a.id < b.id ? -1 : 1)));
    const rev = hsResolve(list.slice().reverse(), C, R, pin);                                    // the order of the input does not matter
    if (norm(rev) !== norm(r)) res.orderDependent++;
    if (pin) { const f = hsFit(list.find(t => t.id === pin), C, R), g = r.find(t => t.id === pin); if (JSON.stringify(f) !== JSON.stringify(g)) res.pinMoved++; }
  }
}
console.log(JSON.stringify(res));
""")
        self.assertEqual(out["cases"], 120)
        self.assertEqual(out["bad"], [])
        self.assertEqual(out["lost"], 0)
        self.assertEqual(out["notIdempotent"], 0)
        self.assertEqual(out["orderDependent"], 0)
        self.assertEqual(out["pinMoved"], 0)            # the tile you are moving keeps the place you gave it

    def test_full_page_continues_on_the_next(self):
        out = self._run("""
// five tiles that each fill a whole page of a 6 column, 4 row screen
const list = ['a', 'b', 'c', 'd', 'e'].map(id => ({ id, p: 0, a: 'l', x: 0, y: 0, w: 6, h: 4 }));
const r = hsResolve(list, 6, 4);
console.log(JSON.stringify(r.map(t => [t.id, t.p, t.y])));
""")
        self.assertEqual(out, [["a", 0, 0], ["b", 1, 0], ["c", 2, 0], ["d", 3, 0], ["e", 4, 0]])

    def test_place_moves_and_size_keeps_the_left_edge(self):
        out = self._run("""
const m = hsMetrics(1440, 800), items = WIDGETS.filter(w => !w.off).map(w => { const [cw, ch] = wSize(w, w.size); return { id: w.id, w: cw, h: ch, side: w.side }; });
const list = hsPack(items, m.C, m.R, m.Z);
const moved = hsPlace(list, 'calendar', 5, 2, 0, m.C, m.R), c = moved.find(t => t.id === 'calendar');
const far = hsPlace(list, 'calendar', 500, 500, 0, m.C, m.R).find(t => t.id === 'calendar');
const hero0 = list.find(t => t.id === 'hero');
const bigList = hsSize(list, 'hero', 99, 99, m.C, m.R), big = bigList.find(t => t.id === 'hero');
const small = hsSize(list, 'hero', 2, 2, m.C, m.R).find(t => t.id === 'hero');
console.log(JSON.stringify({ C: m.C, R: m.R, moved: [hsLeft(c, m.C), c.y, c.p], movedBad: bad(moved, m.C, m.R),
  far: [hsLeft(far, m.C) + far.w, far.y + far.h], big: [hsLeft(big, m.C) + big.w, big.y + big.h], bigBad: bad(bigList, m.C, m.R),
  small: [hsLeft(small, m.C) === hsLeft(hero0, m.C), small.w, small.h] }));
""")
        self.assertEqual(out["moved"], [5, 2, 0])
        self.assertEqual(out["movedBad"], [])
        self.assertEqual(out["far"], [out["C"], out["R"]])        # dragged beyond the screen: it ends at the corner
        self.assertLessEqual(out["big"][0], out["C"])
        self.assertLessEqual(out["big"][1], out["R"])
        self.assertEqual(out["bigBad"], [])
        self.assertEqual(out["small"], [True, 2, 2])

    def test_slot_hugs_the_edge_of_its_side(self):
        out = self._run("""
const C = 17, R = 8, Z = 4;
const l = hsSlot([], 4, 3, 'l', C, R, Z), r = hsSlot([], 4, 3, 'r', C, R, Z);
const r2 = hsSlot([hsMake('x', 0, r.col, r.y, 4, 3, C)], 4, 3, 'r', C, R, Z);
// the right zone is full from top to bottom: the next tile goes to the left zone of the same page, before a new page
const right = [hsMake('a', 0, C - 4, 0, 4, 3, C), hsMake('b', 0, C - 4, 3, 4, 3, C)];
const spill = hsSlot(right, 4, 3, 'r', C, R, Z);
// ... and when that is full, too, to the next page
const both = right.concat([hsMake('c', 0, 0, 0, 4, 3, C), hsMake('d', 0, 0, 3, 4, 3, C), hsMake('e', 0, 0, 6, 4, 2, C), hsMake('f', 0, C - 4, 6, 4, 2, C)]);
console.log(JSON.stringify({ l, r, r2, spill, next: hsSlot(both, 4, 3, 'l', C, R, Z) }));
""")
        self.assertEqual(out["l"], {"p": 0, "col": 0, "y": 0})
        self.assertEqual((out["r"]["col"] + 4, out["r"]["y"], out["r"]["p"]), (17, 0, 0))      # right zone: against the right edge
        self.assertEqual((out["r2"]["col"] + 4, out["r2"]["y"], out["r2"]["p"]), (17, 3, 0))   # then below it
        self.assertEqual(out["spill"], {"p": 0, "col": 0, "y": 0})                            # no room on its side: the other zone
        self.assertEqual(out["next"]["p"], 1)                                                  # nothing left on the page

    def test_empty_pages_close(self):
        out = self._run("console.log(JSON.stringify(hsCompact([{ p: 0 }, { p: 2 }, { p: 5 }, { p: 2 }]).map(t => t.p)));")
        self.assertEqual(out, [0, 1, 2, 1])

    # ---- the default arrangement
    def test_default_arrangement_fits_every_screen(self):
        out = self._run("""
const rows = [];
for (const [W, H] of [[1180, 620], [1280, 720], [1366, 768], [1440, 800], [1536, 730], [1920, 1080], [2560, 1440], [3840, 2160]]) {
  const m = hsMetrics(W, H);
  const items = WIDGETS.filter(w => !w.off).map(w => { const [cw, ch] = wSize(w, w.size); return { id: w.id, w: cw, h: ch, side: w.side }; });
  const list = hsPack(items, m.C, m.R, m.Z);
  const inZone = t => { const l = hsLeft(t, m.C); return l + t.w <= m.Z || l >= m.C - m.Z; };
  rows.push({ W, H, n: list.length, want: items.length, bad: bad(list, m.C, m.R), outside: list.filter(t => !inZone(t)).map(t => t.id),
    fixed: JSON.stringify(hsResolve(list, m.C, m.R)) === JSON.stringify(list), pages: Math.max(...list.map(t => t.p)) + 1,
    first: list.filter(t => t.p === 0).map(t => t.id), hero: byId(list).hero, calendar: byId(list).calendar });
}
console.log(JSON.stringify(rows));
""")
        for r in out:
            tag = f"{r['W']}x{r['H']}"
            self.assertEqual(r["n"], r["want"], tag)
            self.assertEqual(r["bad"], [], tag)
            self.assertEqual(r["outside"], [], tag)       # nothing ever sits in the middle, over the galaxy
            self.assertTrue(r["fixed"], tag)              # the default is already a fixed point of the resolver
            self.assertLessEqual(r["pages"], 5, tag)
            self.assertIn("hero", r["first"], tag)        # the greeting is on the first page, top left
            self.assertEqual((r["hero"]["p"], r["hero"]["a"], r["hero"]["x"], r["hero"]["y"]), (0, "l", 0, 0), tag)
            self.assertEqual((r["calendar"]["p"], r["calendar"]["a"], r["calendar"]["x"], r["calendar"]["y"]), (0, "r", 0, 0), tag)
            if r["H"] >= 720:                             # ... and so is the quick launch, below the key figures, wherever its two rows fit
                self.assertIn("launch", r["first"], tag)
        # a bigger screen shows more of it at once: the zones are at most 8 columns wide, so that the galaxy keeps the middle
        pages = {(r["W"], r["H"]): r["pages"] for r in out}
        self.assertLessEqual(pages[(1920, 1080)], pages[(1280, 720)])
        self.assertLessEqual(pages[(2560, 1440)], pages[(1920, 1080)])
        self.assertLessEqual(pages[(3840, 2160)], 2)
        self.assertLessEqual(pages[(1180, 620)], 4)      # the smallest wide screen: four pages at most

    def test_old_columns_are_arranged_once_and_then_belong_to_the_homescreen(self):
        out = self._run("""
const m = hsMetrics(1440, 800);
TV.layout = { v: LAYOUT_V, hidden: ['costs', 'clocks', 'needs'], tiles: null, flow: null,
  legacy: { order: ['apps', 'hero'], col: { apps: 'r' }, size: { hero: 'l' } } };
const t = TV.baseTiles(m), by = byId(t);
console.log(JSON.stringify({ ids: t.map(x => x.id).sort(), bad: bad(t, m.C, m.R), apps: by.apps, hero: by.hero, heroL: wSize(WIDGET_BY_ID.get('hero'), 2) }));
""")
        self.assertNotIn("needs", out["ids"])                   # hidden stays hidden
        self.assertNotIn("costs", out["ids"])
        self.assertEqual(len(out["ids"]), 17)                   # the 18 widgets that are on by default, without "needs"
        self.assertEqual(out["bad"], [])
        apps = out["apps"]
        self.assertEqual((apps["a"], apps["p"], apps["y"], apps["x"]), ("r", 0, 0, 0))   # first in the old order, moved to the right: top right
        self.assertEqual(out["hero"]["h"], out["heroL"][1])                              # size "l" of the old layout is size L now
        self.assertEqual(out["hero"]["a"], "l")

    def test_saved_tiles_survive_a_smaller_screen_and_new_widgets_find_a_place(self):
        out = self._run("""
// saved on a large screen (C = 30), opened on a smaller one: nothing leaves the screen, nothing overlaps
const saved = {};
const ids = WIDGETS.filter(w => !w.off).map(w => w.id);
ids.forEach((id, k) => { saved[id] = { p: 0, a: k % 2 ? 'r' : 'l', x: ri(0, 28), y: ri(0, 14), w: 6, h: ri(2, 6) }; });
delete saved.goals; delete saved.runs;                      // two widgets the saved layout does not know yet
TV.layout = { v: LAYOUT_V, hidden: ['costs', 'clocks'], tiles: saved, legacy: null, flow: null };
const m = hsMetrics(1280, 720), t = TV.baseTiles(m);
TV.layout = { v: LAYOUT_V, hidden: ['costs', 'clocks', 'hero'], tiles: { hero: { p: 0, a: 'l', x: 0, y: 0, w: 6, h: 4 } }, legacy: null, flow: null };
console.log(JSON.stringify({ n: t.length, bad: bad(t, m.C, m.R), has: ['goals', 'runs'].map(id => t.some(x => x.id === id)),
  heroHidden: !TV.baseTiles(m).some(x => x.id === 'hero') }));
""")
        self.assertEqual(out["n"], 18)
        self.assertEqual(out["bad"], [])
        self.assertEqual(out["has"], [True, True])
        self.assertTrue(out["heroHidden"])                 # a hidden widget does not come back because a tile was saved for it

    # ---- the narrow layout
    def test_flow_order_is_its_own_list(self):
        out = self._run("""
const ids = WIDGETS.filter(w => !w.off).map(w => w.id);
TV.tiles = ids.filter(id => id !== 'goals').map(id => ({ id }));   // goals is hidden
TV.layout = { flow: null };
const base = TV.flowOrder();
TV.layout = { flow: ['calendar', 'zz', 'goals', 'hero'] };
const own = TV.flowOrder();
console.log(JSON.stringify({ base, own, expect: ids.filter(id => id !== 'goals') }));
""")
        self.assertEqual(out["base"], out["expect"])                       # no own order yet: the order of the widget list
        self.assertEqual(out["own"][:2], ["calendar", "hero"])             # your order first, unknown and hidden ids dropped
        self.assertEqual(sorted(out["own"]), sorted(out["expect"]))        # every shown widget exactly once
        self.assertEqual(len(out["own"]), len(set(out["own"])))

    # ---- what fits a tile: the blocks of a widget come back in order of importance
    FIT = """
// a block is { rank, rows, h }: h the height of a plain block (of one row for a list); used(st) the height of a state
const heights = blocks => st => st.reduce((s, x, i) => s + (x.on ? (blocks[i].rows ? x.rows * blocks[i].h : blocks[i].h) : 0), 0);
const plan = (blocks, room) => { const used = heights(blocks); return fitPlan(blocks, st => used(st) > room); };
const show = (blocks, room) => plan(blocks, room).map(x => (x.on ? (x.rows || 'on') : 'off'));
"""

    def test_fit_plan_brings_blocks_back_by_importance_and_rows_one_at_a_time(self):
        out = self._run(self.FIT + """
const B = [{ rank: 3, rows: 0, h: 40 }, { rank: 1, rows: 5, h: 20 }, { rank: 2, rows: 0, h: 30 }, { rank: 4, rows: 0, h: 50 }];
const L = [{ rank: 1, rows: 3, h: 30 }, { rank: 2, rows: 4, h: 25 }];
const T = [{ rank: 2, rows: 0, h: 30 }, { rank: 2, rows: 0, h: 30 }];
const K = [{ rank: 1, rows: 2, h: 20 }, { rank: 2, rows: 0, h: 50 }, { rank: 3, rows: 0, h: 10 }];
console.log(JSON.stringify({
  B: [1000, 200, 130, 100, 55, 10, 0].map(r => show(B, r)),
  L: [10, 60, 100, 115, 140, 190].map(r => show(L, r)),
  T: show(T, 40), K: show(K, 55), none: fitPlan([], () => true) }));
""")
        self.assertEqual(out["B"], [["on", 5, "on", "on"],      # room for everything
                                    ["on", 5, "on", "off"],     # the least important plain block is the first to leave
                                    ["off", 5, "on", "off"],
                                    ["off", 5, "off", "off"],   # the list (rank 1) keeps all its rows before anything else is considered
                                    ["off", 2, "off", "off"],   # a list gives up its last rows one by one
                                    ["off", 1, "off", "off"],   # ... but a list of rank 1 keeps its first row, whatever the room
                                    ["off", 1, "off", "off"]])
        self.assertEqual(out["L"], [[1, "off"],                 # a rank 2 list leaves as a whole when not even one row fits ...
                                    [2, "off"],
                                    [3, "off"],
                                    [3, 1],
                                    [3, 2],                     # ... and otherwise shows as many rows as fit
                                    [3, 4]])
        self.assertEqual(out["T"], ["on", "off"])               # equal rank: by position
        self.assertEqual(out["K"], [2, "off", "on"])            # a block that does not fit is skipped, a smaller one after it may still fit
        self.assertEqual(out["none"], [])

    def test_fit_plan_never_overflows_and_leaves_nothing_that_would_still_fit(self):
        out = self._run(self.FIT + """
const res = { cases: 0, bad: [] };   // (rnd and ri: the seeded generator of the harness)
for (let c = 0; c < 600; c++) {
  const n = ri(1, 7), B = Array.from({ length: n }, () => ({ rank: ri(1, 5), rows: rnd() < 0.5 ? ri(1, 8) : 0, h: ri(8, 60) })), room = ri(0, 420);
  const used = heights(B), st = plan(B, room), u = used(st), tag = JSON.stringify({ B, room });
  res.cases++;
  if (st.length !== n) { res.bad.push('length ' + tag); continue; }
  st.forEach((x, i) => {
    if (!x.on && x.rows !== 0) res.bad.push('rows of a block that is off ' + tag);
    if (x.rows > B[i].rows) res.bad.push('too many rows ' + tag);
    if (x.on && B[i].rows && x.rows < 1) res.bad.push('list on without a row ' + tag);
  });
  // an overflow is only ever the first row of a list of rank 1 (kept whatever happens): without those the plan fits
  const core = st.map((x, i) => (B[i].rows && B[i].rank <= 1 && x.on && x.rows === 1 ? { on: false, rows: 0 } : x));
  if (used(core) > room) res.bad.push('overflow ' + used(core) + ' > ' + room + ' ' + tag);
  // maximal: switching one more block on, or showing one more row, would overflow
  st.forEach((x, i) => {
    const more = st.map(y => ({ on: y.on, rows: y.rows }));
    if (!x.on) { more[i] = { on: true, rows: B[i].rows ? 1 : 0 }; if (used(more) <= room) res.bad.push('block ' + i + ' still fits ' + tag); }
    else if (B[i].rows && x.rows < B[i].rows) { more[i].rows++; if (used(more) <= room) res.bad.push('row of ' + i + ' still fits ' + tag); }
  });
  // pure: the same input, the same plan
  if (JSON.stringify(plan(B, room)) !== JSON.stringify(st)) res.bad.push('not deterministic ' + tag);
}
console.log(JSON.stringify(res));
""")
        self.assertEqual(out["cases"], 600)
        self.assertEqual(out["bad"], [])

    # ---- how see-through the widgets are: matte .. the look they had .. liquid
    def test_glass_tokens_run_from_matte_through_the_old_look_to_liquid(self):
        out = self._run("""
const at = v => glassTokens(v), keys = Object.keys(GLASS_STOPS);
const sweep = Array.from({ length: 101 }, (_, v) => at(v));
const mono = (k, dir) => sweep.every((t, i) => i === 0 || (dir > 0 ? t[k] >= sweep[i - 1][k] - 1e-9 : t[k] <= sweep[i - 1][k] + 1e-9));
console.log(JSON.stringify({ keys, matte: at(0), def: at(60), liquid: at(100), d: GLASS_DEFAULT, m: GLASS_MATTE, near: at(GLASS_MATTE),
  mono: { a: mono('a', -1), sat: mono('sat', 1), rim: mono('rim', 1), sheen: mono('sheen', 1), shade: mono('shade', 1), refr: mono('refr', 1), disp: mono('disp', 1) },
  blurUp: sweep.slice(0, 61).every((t, i, a) => i === 0 || t.blur >= a[i - 1].blur - 1e-9),
  blurDown: sweep.slice(60).every((t, i, a) => i === 0 || t.blur <= a[i - 1].blur + 1e-9),
  clamp: [at(-5), at(250), at('37'), at(37.6)], t37: at(37), t38: at(38),
  bad: [at(NaN), at(undefined), at(null), at(''), at('abc')],
  ints: [glassClamp(12.4), glassClamp(12.5), glassClamp('7'), glassClamp(101), glassClamp(-1), glassClamp(undefined)],
  text: [glassText(0), glassText(100), glassText(42), glassText(-3), glassText(7)] }));
""")
        self.assertEqual(out["keys"], ["a", "blur", "sat", "rim", "sheen", "shade", "refr", "disp"])
        self.assertEqual(out["d"], 60)
        # the default is the regular glass of Apple's iOS 27 kit: frost 16, saturation 1.8, refraction .7, dispersion .2
        self.assertEqual(out["def"], {"a": 40, "blur": 16, "sat": 1.8, "rim": 0.3, "sheen": 0.06, "shade": 0, "refr": 0.7, "disp": 0.2})
        self.assertEqual(out["matte"], {"a": 96, "blur": 0, "sat": 1, "rim": 0.12, "sheen": 0.02, "shade": 0, "refr": 0.3, "disp": 0.05})   # nearly opaque, no blur
        self.assertEqual(out["liquid"], {"a": 6, "blur": 6, "sat": 2.4, "rim": 0.6, "sheen": 0.16, "shade": 0.55, "refr": 1, "disp": 1})   # almost clear, a lit rim
        for k in ("a", "sat", "rim", "sheen", "shade", "refr", "disp"):
            self.assertTrue(out["mono"][k], k)                   # one direction from matte to liquid
        self.assertTrue(out["blurUp"] and out["blurDown"])       # the blur peaks at the old look: sharp glass is clearer than frosted
        self.assertGreaterEqual(out["near"]["a"], 90)            # the matte step is still a solid pane
        self.assertEqual(out["clamp"][0], out["matte"])
        self.assertEqual(out["clamp"][1], out["liquid"])
        self.assertEqual(out["clamp"][2], out["t37"])            # a stored string is a number
        self.assertEqual(out["clamp"][3], out["t38"])            # whole steps
        for t in out["bad"]:
            self.assertEqual(t, out["def"])                      # nothing or rubbish stored: the default
        self.assertEqual(out["ints"], [12, 13, 7, 100, 0, 60])
        self.assertEqual(out["text"], ["Matte", "Liquid", "42 %", "Matte", "7 %"])

    # ---- fitTile() itself, on a stand-in for the DOM: a node has a height, a list is the sum of its rows
    FAKE_DOM = """
const fakeSimple = (n, s) => (s === 'details[open]' ? n.tag === 'details' && n.open : s[0] === '.' && n.cls.has(s.slice(1)));
class Fake {
  constructor(cls, o = {}) {
    this.cls = new Set(String(cls || '').split(' ').filter(Boolean)); this.kids = []; this.own = o.h || 0; this.tag = o.tag || 'div'; this.open = !!o.open;
    this.parent = null; this.dataset = o.dataset || {}; this.text = ''; this.box = o.box || 0;
    this.classList = { add: c => { this.cls.add(c); }, remove: c => { this.cls.delete(c); }, contains: c => this.cls.has(c),
      toggle: (c, on) => { if (on === undefined ? !this.cls.has(c) : on) this.cls.add(c); else this.cls.delete(c); } };
  }
  get children() { return this.kids; }
  get textContent() { return this.text; }
  set textContent(v) { this.text = v; }
  get scrollHeight() { return this.cls.has('fit-off') ? 0 : this.own + this.kids.reduce((s, k) => s + k.scrollHeight, 0); }
  get clientHeight() { return this.box; }
  append(...ns) { ns.forEach(n => { n.parent = this; this.kids.push(n); }); return this; }
  after(n) { const p = this.parent; n.parent = p; p.kids.splice(p.kids.indexOf(this) + 1, 0, n); }
  remove() { if (this.parent) { this.parent.kids.splice(this.parent.kids.indexOf(this), 1); this.parent = null; } }
  matches(s) { return fakeSimple(this, s); }
  querySelectorAll(s) { const out = [], walk = n => n.kids.forEach(k => { if (fakeSimple(k, s)) out.push(k); walk(k); }); walk(this); return out; }
  querySelector(s) {
    if (s.startsWith(':scope > ')) { let cur = [this]; for (const p of s.slice(9).split(' > ')) cur = [].concat(...cur.map(c => c.kids.filter(k => fakeSimple(k, p)))); return cur[0] || null; }
    return this.querySelectorAll(s)[0] || null;
  }
}
const h = (tag, a) => new Fake((a && a.class) || '', { tag, h: 14 });      // the "+N more" line is 14 px high
const plain = (cls, hh, o = {}) => new Fake(cls, Object.assign({ h: hh }, o));
const list = (cls, n, rowH, headH = 0) => { const l = new Fake(cls, { h: headH }); for (let i = 0; i < n; i++) l.append(new Fake('', { h: rowH })); return l; };
const mount = (id, kids, box) => { const el = new Fake('hs-tile', { dataset: { tile: id } }), card = new Fake('widget'), body = new Fake('w-body', { box });
  el.append(card); card.append(body); kids.forEach(k => body.append(k)); return { el, body }; };
const off = k => k.cls.has('fit-off');
const shown = l => l.kids.filter(k => !off(k)).length;
const mores = b => b.querySelectorAll('.fit-more').map(k => k.text + (off(k) ? ' (off)' : ''));
"""

    def test_fit_tile_trims_a_widget_to_its_box_in_order_of_importance(self):
        out = self._run(self.FAKE_DOM + FIT_SRC + """
// the calendar: clock (never leaves) 60, zones 40, quarter 90, "up next" = heading 20 + 5 rows of 20 (rank 2, a list), schedule 30
const cal = (box, o = {}) => {
  const up = new Fake('cal-up', { h: 20 }), next = list('cal-next', 5, 20); up.append(next);
  const k = [plain('cal-clock', 60), plain('cal-zones', 40, o.open ? { tag: 'details', open: true } : {}), plain('cal-q', 90), up, plain('cal-act', 30)];
  const m = mount('calendar', k, box);
  fitTile(m.el, o.wide !== false);
  return { m, k, next };
};
const sum = c => ({ off: c.k.map(off), rows: shown(c.next), more: mores(c.m.body), height: c.m.body.scrollHeight });
const res = {};
for (const box of [1000, 340, 300, 150, 70]) res['b' + box] = sum(cal(box));
res.open = sum(cal(150, { open: true }));
// the same tile twice: the same result (fitTile starts from a clean slate); and below the wide layout nothing is trimmed
const c = cal(150), first = JSON.stringify(sum(c)); fitTile(c.m.el, true);
res.again = JSON.stringify(sum(c)) === first;
fitTile(c.m.el, false);
res.flow = sum(c);
// a list of rank 1 keeps its first row, however small the box is, and says how many are not shown
const dl = box => { const l = list('dl-cards', 4, 80), m = mount('deadlines', [l], box); fitTile(m.el, true); return { rows: shown(l), more: mores(m.body), height: m.body.scrollHeight }; };
res.dl = [400, 330, 100, 10].map(dl);
// a widget without an entry in the table, a tile without a body
const free = mount('nope', [plain('x', 500)], 50); fitTile(free.el, true);
const hollow = new Fake('hs-tile', { dataset: { tile: 'calendar' } }); fitTile(hollow, true);
res.untouched = [off(free.body.kids[0]), hollow.kids.length];
console.log(JSON.stringify(res));
""")
        self.assertEqual(out["b1000"], {"off": [False] * 5, "rows": 5, "more": [], "height": 340})   # everything fits: nothing is trimmed
        self.assertEqual(out["b340"], out["b1000"])
        self.assertEqual(out["b300"], {"off": [False, False, True, False, False], "rows": 5, "more": [], "height": 250})   # the quarter goes first
        self.assertEqual(out["b150"], {"off": [False, True, True, False, True], "rows": 2, "more": ["+3 more"], "height": 134})
        self.assertEqual(out["b70"], {"off": [False, True, True, True, True], "rows": 0, "more": [], "height": 60})   # only the clock is left
        # a block opened by hand stays and counts: there is no room for the list any more, the schedule still fits
        self.assertEqual(out["open"], {"off": [False, False, True, True, False], "rows": 0, "more": [], "height": 130})
        self.assertTrue(out["again"])
        self.assertEqual(out["flow"], {"off": [False] * 5, "rows": 5, "more": [], "height": 340})
        self.assertEqual(out["dl"][0], {"rows": 4, "more": [], "height": 320})
        self.assertEqual(out["dl"][1], {"rows": 4, "more": [], "height": 320})
        self.assertEqual(out["dl"][2], {"rows": 1, "more": ["+3 more"], "height": 94})
        self.assertEqual(out["dl"][3], {"rows": 1, "more": ["+3 more"], "height": 94})   # over the box, but never empty
        self.assertEqual(out["untouched"], [False, 0])


class HomescreenContractTests(unittest.TestCase):
    """CSS and script wiring that the model tests cannot see."""

    def test_the_media_threshold_is_the_one_of_the_script(self):
        js = re.search(r"const hsWide = \(W, H\) => W >= (\d+) && H >= (\d+);", SCRIPT)
        css = re.search(r"@media \(min-width: (\d+)px\) and \(min-height: (\d+)px\) \{\n  body\.is-home \{ overflow: hidden", HTML)
        self.assertTrue(js and css)
        self.assertEqual(js.groups(), css.groups())

    def test_tiles_move_by_translate_and_effects_use_scale_and_rotate(self):
        self.assertIn(".hs-tile { position: absolute; left: 0; top: 0; margin: 0; pointer-events: auto; container: tile / size; }", HTML)
        self.assertIn("el.style.translate =", VIEW)
        self.assertNotIn("style.transform", VIEW)       # `transform` stays free: scale / rotate pivot on the tile, position does not scale
        for kf, prop in (("hsJelly", "scale"), ("hsPopIn", "scale"), ("hsJiggle", "rotate"), ("hsDrop", "scale")):
            m = re.search(r"@keyframes " + kf + r" \{(.*)\}\n", HTML)
            self.assertTrue(m and (prop + ":") in m.group(1) and "transform" not in m.group(1), kf)

    def test_all_motion_of_the_homescreen_is_inside_the_no_preference_block(self):
        css = HTML[: HTML.index("</style>")]
        # the block that carries the motion of the glass design
        motion = next(b for b in _blocks(css, "@media (prefers-reduced-motion: no-preference)") if "@keyframes hsJelly" in b)
        for needle in ("@keyframes hsJelly", "@keyframes hsPopIn", "@keyframes hsJiggle", "@keyframes hsDrop",
                       ".hs-tile { transition: translate .62s var(--lg-spring)", ".hs-tile.hs-jelly { animation: hsJelly",
                       ".hs-tile.hs-new { animation: hsPopIn", ".editing .hs-tile:not(.hs-drag)", "animation: hsJiggle",
                       ".hs-dot { transition: background"):
            self.assertIn(needle, motion, needle)
            self.assertEqual(css.count(needle), 1, needle)   # and nowhere else: with reduced motion the tiles simply jump
        outside = css.replace(motion, "")
        self.assertNotRegex(outside, r"animation(-name)?:[^;}]*\bhs(Jelly|PopIn|Jiggle|Drop)\b")
        self.assertNotIn("transition: translate .62s", outside)

    def test_scripted_motion_respects_reduced_motion(self):
        self.assertIn("if (!el || RM.matches) return;", VIEW)                                   # the jelly after a drop
        self.assertIn("if (RM.matches) finish(); else { el.classList.add('hs-pop'); setTimeout(finish, 260); }", VIEW)   # hiding
        self.assertIn("behavior: RM.matches ? 'auto' : 'smooth'", VIEW)                          # scrolling a tile into view
        self.assertIn("if (!indFirst && dist > 4 && !RM.matches && ind.animate)", SCRIPT)        # the droplet of the tab bead

    def test_other_pages_are_hidden_inert_and_skipped_by_the_lens(self):
        self.assertIn("el.inert = !on;", VIEW)
        self.assertIn(".hs-tile.hs-off { opacity: 0; scale: .92; visibility: hidden; pointer-events: none; }", HTML)
        self.assertIn("if (el.closest('.hs-off, .hs-matte')) return;", SCRIPT)   # the glass lens does not spend its budget on them (nor on matte panes)

    def test_arrangement_is_saved_locally_in_one_versioned_key(self):
        self.assertIn("const LAYOUT_V = 5;", SCRIPT)
        self.assertIn("store.set('widgets', JSON.stringify({ v: LAYOUT_V, hidden: this.layout.hidden, tiles: this.layout.tiles, flow: this.layout.flow }))", SCRIPT)
        self.assertNotIn("fetch(", VIEW)                              # the homescreen never sends the arrangement anywhere

    def test_arranging_has_a_help_text_for_both_layouts(self):
        self.assertIn("hs-h-wide", VIEW)
        self.assertIn("hs-h-flow", VIEW)
        self.assertIn(".hs-h-wide { display: none; }", HTML)
        self.assertIn(".hs-h-wide { display: inline; } .hs-h-flow { display: none; }", HTML)

    def test_the_stage_is_see_through_and_cheap(self):
        # moving colour behind the glass, as soft discs: no 96px blur filter that the glass would have to re-sample every frame
        self.assertIn("body.is-home .bg i { opacity: .3; filter: none; }", HTML)
        for k in (1, 2, 3):
            self.assertIn(f"body.is-home .bg i:nth-child({k}) {{ background: radial-gradient(closest-side, var(--aurora-{k})", HTML)
        self.assertIn("body.is-home .hs-wrap { position: fixed; inset: 0;", HTML)   # the stars run across the whole screen, behind the tiles

    def test_tab_bead_is_a_droplet(self):
        self.assertIn("ind.style.translate = b.offsetLeft + 'px 0';", SCRIPT)
        self.assertIn("ind.style.translate = '0 ' + b.offsetTop + 'px';", SCRIPT)
        self.assertIn("ind.animate([{ scale: '1 1' }", SCRIPT)
        self.assertEqual(len(re.findall(r"\.tab-ind \{[^}]*transition: translate \.45s", HTML)), 1)
        self.assertNotRegex(HTML, r"\.tab-ind \{[^}]*transition: transform")

    def test_the_skills_matrix_is_brought_into_view_inside_its_tile(self):
        self.assertRegex(SCRIPT, r"querySelector\('\.mx'\); if \(m\) m\.scrollIntoView\(\{ block: 'start'")

    def test_the_view_builds_no_html_from_strings(self):
        for bad in (".innerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write"):
            self.assertNotIn(bad, VIEW)

    # ---- widgets adapt to the size of their tile
    def test_fit_table_names_real_widgets_and_blocks_that_the_builders_make(self):
        table = _between("const WIDGET_FIT = {", "// Fit the content of one tile")
        ids = re.findall(r"^  (\w+): \[", table, re.M)
        self.assertGreaterEqual(len(ids), 12)
        self.assertLessEqual(set(ids), set(re.findall(r"id: '(\w+)'", WIDGETS)))     # no entry for a widget that does not exist
        blocks = set(re.findall(r"\['(\.[\w-]+)'", table)) | set(re.findall(r"', \d, '(\.[\w-]+)'\]", table))
        self.assertGreaterEqual(len(blocks), 25)
        for sel in sorted(blocks):                                                   # ... nor a block that no builder gives that class
            self.assertRegex(SCRIPT, r"class: '[^']*\b" + re.escape(sel[1:]) + r"\b", sel)
        for rank in re.findall(r"', (\d)[,\]]", table):
            self.assertTrue(1 <= int(rank) <= 5)

    def test_the_fit_engine_is_wired_to_every_change_of_size(self):
        self.assertIn("el.dataset.tile", FIT_SRC)
        self.assertIn("if (el._fit !== key) { el._fit = key; fitTile(el, true); }", SCRIPT)   # a new box: fit again, an unchanged one: nothing
        self.assertIn("if (el._fit) { el._fit = ''; fitTile(el, false); }", SCRIPT)           # the flow layout is as tall as its content
        self.assertIn("document.fonts.ready.then(", SCRIPT)                                    # late fonts change what fits
        self.assertIn("grid.addEventListener('toggle'", SCRIPT)                                # an opened <details> changes it, too
        self.assertIn("fitPlan(blocks, st => { show(st); return body.scrollHeight > body.clientHeight + 1; })", FIT_SRC)
        # what the engine switches off, and its "+N more" line
        self.assertIn(".fit-off { display: none !important; }", HTML)
        self.assertRegex(HTML, r"\.fit-more \{[^}]*font: 600 12px var\(--font\)")

    def test_container_units_only_where_the_tile_is_the_container(self):
        css = HTML[: HTML.index("</style>")]
        spans = []
        for inner in _blocks(css, "@container tile"):
            spans.append(inner)
        self.assertEqual(len(spans), 11)
        self.assertIn("@container tile (min-width: 0px) {", css)    # the fluid type: only inside a tile container
        unit = re.compile(r"\d(?:cq(?:w|h|i|b|min|max))\b")
        inside = "".join(spans)
        self.assertGreaterEqual(len(unit.findall(inside)), 10)
        outside = css
        for b in spans:
            outside = outside.replace(b, "")
        # outside the tile blocks only the costs figures use them, and they are containers themselves (container-type: inline-size)
        for rule in re.findall(r"([^{}]*)\{[^{}]*" + unit.pattern + r"[^{}]*\}", outside):
            self.assertIn(".cost-fig", rule)
        self.assertRegex(HTML, r"\.cost-fig \{[^}]*container-type: inline-size")
        # the tiles are size containers in the wide layout only (below it they are as tall as their content)
        self.assertIn("container: tile / size;", HTML)

    def test_quick_launch_reaches_every_view_from_the_home_page(self):
        # the home page has no tab bar: this tile is the way to every view from there, made from the same list as the tabs
        buttons = _between("function launchButtons() {", "function launchCard() {")
        card = _between("function launchCard() {", "// Calendar: analog clock")
        self.assertIn("VIEWS.filter(v => v.id !== 'today')", buttons)
        self.assertIn("showView(v.id, { focus: true })", buttons)
        self.assertIn("'aria-label': v.label", buttons)              # the short tile shows the icons only
        self.assertIn("launchButtons()", card)
        self.assertIn("'aria-label': tr('Quick launch')", card)      # not "Apps": that is the name of another widget
        self.assertRegex(WIDGETS, r"id: 'launch', label: tr\('Quick launch'\), side: 'l', sizes: \[\[6, 2\], \[6, 3\], \[6, 4\]\]")
        # names only where the whole grid with names fits: narrow tiles need 2 rows (4 columns from 350 px wide), short ones none; the rest scrolls
        self.assertRegex(HTML, r"@container tile \(\(max-width: 349px\) and \(max-height: 239px\)\) or \(\(min-width: 350px\) and \(max-height: 159px\)\) \{[^@]*\.launch-t \{ display: none; \}")
        self.assertIn(".launch-card { display: grid; align-content: center; overflow: auto;", HTML)
        # below 1100 px the tab bar hides its icons; the same svg inside an app icon (this tile, the Apps list) has to stay
        self.assertIn(".app-ico .tab-ico { display: block; }", HTML)

    def test_the_apps_menu_has_its_own_keys_and_stays_open_over_a_refresh(self):
        bar = _between("const apps = h('details'", "const info = ib(")
        self.assertIn("open: view.appsOpen || null", bar)
        self.assertIn("view.appsOpen = apps.open", bar)
        self.assertIn("'apps:'", bar)                    # not the go: keys of the Quick launch tile: focus is restored by key
        self.assertIn("ae.closest('.w-menu[open]')", SCRIPT)   # Escape closes the menu that has the focus, not the first one

    def test_the_collapsed_search_is_not_wider_than_its_box(self):
        # In the dock the search is only an icon until it has the focus. Padding on the collapsed input made it 44 px wide in a 34 px
        # box, and it covered the Refresh button next to it.
        rule = re.search(r"body\.is-home \.search input \{([^}]*)\}", HTML).group(1)
        self.assertIn("padding: 0;", rule)
        self.assertNotIn("padding-left", rule)
        self.assertIn("body.is-home .search:focus-within input { padding: 0 8px 0 var(--corner); }", HTML)

    def test_the_corner_buttons_are_equal_circles(self):
        # Search, Refresh, Glass and Theme were 34, 40, 44 and 37 px wide pills: one size, a circle, 44 px under a finger.
        self.assertIn("body.is-home { --corner: 40px; }", HTML)
        self.assertIn("@media (pointer: coarse) { body.is-home { --corner: 44px; } }", HTML)
        btn = re.search(r"body\.is-home header\.top \.btn \{([^}]*)\}", HTML).group(1)
        for decl in ("width: var(--corner);", "height: var(--corner);", "padding: 0;"):
            self.assertIn(decl, btn)
        self.assertIn("body.is-home .search { margin: 0; flex: 0 0 auto; width: var(--corner);", HTML)
        self.assertIn("body.is-home .search input { height: var(--corner);", HTML)

    def test_every_widget_has_a_minimum_and_resizing_respects_it(self):
        mins = {i: (int(c), int(r)) for i, c, r in re.findall(r"id: '([\w-]+)'[^\n]*?min: \[(\d+), (\d+)\]", WIDGETS)}
        ids = re.findall(r"id: '([\w-]+)'", WIDGETS)
        # every widget that has content to trim says how small it may get; the four number tiles take the default of 2 x 2
        self.assertEqual(sorted(set(ids) - set(mins)), ["k-needs", "k-notes", "k-reach", "k-routines"])
        self.assertTrue(all(c >= 2 and r >= 2 for c, r in mins.values()))
        self.assertIn("const wMin = (def, t) => { const m = def.min || [2, 2];", SCRIPT)
        self.assertIn("const wmin = wMin(def, t0);", SCRIPT)                       # dragging the corner handle stops at it
        self.assertIn("const min = wMin(WIDGET_BY_ID.get(id), t);", SCRIPT)        # so do the keyboard steps

    # ---- how see-through the widgets are (the slider in the customise menu)
    def test_the_default_of_the_slider_is_the_look_the_widgets_had(self):
        # the stage's glass tokens in the stylesheet are the default stop of the slider (40 %, 16 px, 1.8, .3, .06): the material of the kit
        m = re.search(r"--lg-a: 40%;[^\n]*--lg-rim: rgba\(255,255,255,\.3\); --lg-sheen: \.06;\n\s*--lg-blur: 16px; --lg-sat: 1\.8;", HTML)
        self.assertTrue(m)
        self.assertIn("const GLASS_STOPS = { a: [96, 40, 6], blur: [0, 16, 6], sat: [1, 1.8, 2.4], rim: [0.12, 0.3, 0.6], sheen: [0.02, 0.06, 0.16], shade: [0, 0, 0.55], refr: [0.3, 0.7, 1], disp: [0.05, 0.2, 1] };", SCRIPT)
        self.assertIn("const GLASS_DEFAULT = 60, GLASS_MATTE = 4;", SCRIPT)

    def test_the_slider_lives_in_the_customise_menu_and_in_the_arranging_bar(self):
        bar = _between("function homeBar(view) {", "// What gives way first when a tile is smaller")
        menu = bar[bar.index("const menu = h('details'"): bar.index("menu.addEventListener('toggle'")]
        self.assertIn("glassControl(view, false)", menu)                           # the full control, first in the menu
        self.assertLess(menu.index("glassControl(view, false)"), menu.index("'Widgets'"))
        self.assertIn("view.editing ? glassControl(view, true) : null", bar)       # the compact one while arranging
        self.assertIn("title: tr('Customise: appearance, see-through and visible widgets')", bar)
        ctl = _between("function glassControl(view, compact) {", "// The buttons at the top")
        for needle in ("type: 'range'", "min: 0, max: 100, step: 1", "'aria-label': tr('See-through, from matte to liquid')",
                       "view.setGlass(+range.value, false)",       # while dragging: look only
                       "view.setGlass(+range.value, true)",        # on release: remember it
                       "view.setGlass(GLASS_DEFAULT, true)",       # double-click and the Default button
                       "disabled: flat || null"):
            self.assertIn(needle, ctl, needle)
        self.assertIn("'Matte'", ctl)
        self.assertIn("'Liquid'", ctl)

    def test_the_setting_is_remembered_by_this_browser_only_through_the_store(self):
        self.assertEqual(len(re.findall(r"store\.get\('widgetGlass'\)", SCRIPT)), 1)
        self.assertEqual(len(re.findall(r"store\.set\('widgetGlass', String\(v\.glass\)\)", SCRIPT)), 1)
        self.assertEqual(SCRIPT.count("widgetGlass"), 2)                              # no other place knows the key
        self.assertNotRegex(SCRIPT, r"localStorage[^\n]*widgetGlass")
        self.assertNotIn("widgetGlass", SCRIPT[SCRIPT.index("function loadLayout("): SCRIPT.index("const TodayView = {")])   # not part of the layout blob
        self.assertNotIn("widgetGlass", _between("  save() {", "  // See-through: the tokens go on the grid"))
        self.assertIn("v.glass = glassClamp(store.get('widgetGlass'));", SCRIPT)     # a stored rubbish value is the default

    def test_the_tokens_reach_the_panes_and_flat_glass_wins(self):
        apply_ = _between("function glassApply(grid, v, flat) {", "// The control: a slider")
        self.assertIn("grid.classList.toggle('hs-matte', !flat && v <= GLASS_MATTE);", apply_)
        self.assertIn("if (flat) { GLASS_VARS.forEach(n => grid.style.removeProperty(n)); return; }", apply_)   # Flat stays what Flat is
        for var in ("--lg-a", "--lg-blur", "--lg-sat", "--lg-rim", "--lg-sheen", "--hs-shade"):
            self.assertIn(f"'{var}'", apply_ + "const GLASS_VARS" + SCRIPT[SCRIPT.index("const GLASS_VARS"): SCRIPT.index("function glassApply(")])
        self.assertIn("glassApply(grid, view.glass, LG.mode === 'flat');", SCRIPT)               # on every build of the grid
        self.assertIn("v.offGlass = bus.on('glass', () => v.paintGlass());", SCRIPT)             # ... and when the glass mode changes
        self.assertIn("if (this.offGlass) this.offGlass();", SCRIPT)                             # (and the listener goes with the view)
        # the panes read the tokens from the grid; at the matte end they have no backdrop filter at all; near liquid text gets a shadow
        self.assertIn(".hs-grid .widget { text-shadow: 0 1px 3px rgba(0, 0, 0, var(--hs-shade, 0)); }", HTML)
        self.assertRegex(HTML, r"html:root body \.hs-grid\.hs-matte :is\(\.card, \.kpi, \.deadline, \.hero\) \{[^}]*backdrop-filter: none;")
        self.assertIn("if (el.closest('.hs-off, .hs-matte')) return;", SCRIPT)                   # no lens work for matte panes


if __name__ == "__main__":
    unittest.main()
