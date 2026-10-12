# Design: liquid glass

The dashboard is a set of rounded panes that float over deep space. This page explains how that look is built, what it costs, how it degrades, and how to change it. It is for contributors; the user-facing part is one button in the header (**Lens / Frost / Flat**).

Everything lives in `aos/web/dashboard.html`: the style block "Liquid glass" (last in `<style>`, on purpose) and the script section "5c. Liquid glass" (`LG`). There is no build step and no dependency.

## The three steps

| Mode | What you see | Needs |
|---|---|---|
| **Lens** | Frosted glass plus real refraction at the rim: what lies behind a piece bends at its edge (small pieces also split the colours a little). The widgets of the home page are painted by the graphics card ("The glass of the widgets" below); small controls get an SVG lens. | WebGL2 for the widgets (every current browser), a Chromium based browser for the small controls (Chrome, Edge, Opera, Brave, ...). |
| **Frost** | Backdrop blur, saturation, a lit top edge, a soft drop. No refraction. | `backdrop-filter`. |
| **Flat** | Nearly opaque tint, no backdrop effect at all. | Nothing. |

`<html data-glass="lens|frost|flat">` carries the step; every rule in the glass block reads it through custom properties, so there is one code path, not three.

How the step is chosen (`lgMode`, unit-tested):

1. A stored choice (header button, `localStorage` key `aos.glass`) wins.
2. Otherwise `prefers-reduced-transparency: reduce` gives **Flat**.
3. Otherwise **Lens**, or **Frost** where neither lens can be drawn (no WebGL2 and no Chromium). The header button then cycles Frost, Flat only; it never offers a switch that does nothing.

A browser without `backdrop-filter` at all gets the tint of "flat" through an `@supports not (...)` rule.

## What is a pane, what is a control

| Kind | Elements | Radius | Surface |
|---|---|---|---|
| Pane | `.card`, `.kpi`, `.deadline`, `.ag-card`, hero | 26 px (`--lg-r`), small ones 18 px | frost + lit rim + drop shadow |
| Control | `.btn`, `.icon-btn`, `.os-ibtn`, `.os-btn`, `.hs-atlas`, `.chip`, `.pill`, search field, `.os-seg` | capsule / disc | lighter tint, hover highlight that follows the pointer, press scale |
| Tab tray | `.tabs` with the bead `.tab-ind` | capsule | the bead is the lens |
| Popup | `.detail`, `.results`, `.w-pop`, `.hs-card`, `.os-card`, `.os-preview`, `.os-controls`, `.os-legendbox`, `.tip`, `.note` | 18 / 26 px | denser tint (`--lg-a-pop`) so text never depends on what is behind it |
| Inset | tiles, rows, fields inside a pane | 12 px (`--lg-r-s`) | translucent ink, no backdrop of their own |

Tokens (all in `:root`, dark values in the three dark places: explicit dark theme, system dark, and the OS stage which is dark in every theme):

```
--lg-r 26px  --lg-r-m 18px  --lg-r-s 12px  --lg-gap 16px
--lg-blur 18px  --lg-sat 1.6
--lg-a / --lg-a-pop / --lg-a-ctl   how much of the surface colour a pane / popup / control keeps
--lg-rim  --lg-sheen              lit edge, strength of the diagonal sheen
--lg-over                         tint of one pane (amber / red deadlines, error / ok notes)
--wc                              colour of one pane (accent, cyan, violet, pink); always a token, never a literal
```

## The lens

A lens is an SVG filter used as a backdrop filter: `backdrop-filter: url(#lgN) blur(...) saturate(...)`.

1. `lgLensMap(w, h, r, bezel)` computes a displacement map from the signed distance of the rounded rectangle. Inside the shape and beyond the rim the pixel is neutral grey (128). In the rim the red and green channels lean along the outward normal, strongest at the very edge (`(1 - t)^2`, `t` = depth / bezel).
2. The map becomes a PNG `data:` URL (the page CSP allows `img-src data:`), used by `feImage`, and `feDisplacementMap` shifts the backdrop with it.
3. Pieces up to 9000 css px² also get **chromatic dispersion**: three displacement passes (scale x1, x0.92, x0.84), one per colour channel, added back with two `feBlend screen`.
4. The filter is built in the element's own, unscaled pixels (`offsetWidth`, not the bounding box): a tile that is lifted while you drag it, or wobbles after a drop, is scaled by CSS and the filter must not be rebuilt for that.
5. Filters are cached by size and radius (LRU, 160 entries), so twenty chips of the same width share one.

The engine sets exactly three custom properties on a lensed element (`--lg-f`, `--lg-bc`, `--lg-blur`) and removes them again; the CSS reads them with fallbacks, which is why frost is simply "the lens variable is empty". `tests/test_liquid_glass.py` checks both sides against each other.

## The glass of the widgets

On the home page the tiles are over the galaxy, which is where a refracting pane is worth having, and they are as big as a window: an SVG lens would cost more than the whole stage. So there the glass is painted by the graphics card, in one pass (`createGlassPass`, a WebGL2 canvas laid over the stage canvas and under the tiles):

1. The stage is painted as usual (galaxy, dust, ball glows) into its 2D canvas.
2. That canvas is copied into a texture and its mip levels are generated. The mip levels are the blur: a sample at level 4.5 is a smooth blur about as wide as the 11 px the slider asks for, for the price of one texture read.
3. The stage canvas is cut open under every visible tile (`destination-out`, rounded rectangles), so the unbent picture does not show through.
4. Every tile is drawn once as a rounded rectangle that shows the texture, bent at the edge, saturated and lit. Edge anti-aliasing and the tile's current opacity (a tile that fades out takes its glass with it) are part of the same pass.

The pane in the DOM keeps its tint, border and text and has **no backdrop filter** while the pass runs (`.hs-grid.hs-glx`); its own lit top edge is dropped (`--lg-rim: transparent`) because the pass draws one all the way round.

### How the bend works (what the look is made of)

Apple has not published how Liquid Glass is drawn; the following is the community's reverse engineering of what it looks like, and this is a reimplementation of that idea, not Apple's code.

| Part | Here |
|---|---|
| Shape | The pane is a rounded rectangle (signed distance field). Its rim, the **bezel** (`glassBezel`: 0.9 of the corner radius, at most 0.3 of the short side and 30 css px), is the only part that bends light; inside it the glass is flat. |
| Profile | The bezel is a convex "squircle": height `y = (1 - (1 - x)^4)^(1/4)` with `x` the depth into the rim. It is vertical at the very edge and flat inside. |
| Bend | The slope gives the angle at which a ray from the eye meets the surface. **Snell's law** for glass of index 1.5 turns it into a shift (`glassShift`): about one bezel width at the edge, nothing in the flat. The ray came from further inside, so the rim shows the interior folded back, as a glass bead does. |
| Dispersion | Red, green and blue are bent by slightly different amounts (up to 14 % of the shift), only inside the rim. |
| Light | A key light from the upper left (it follows the pointer a little) and a weaker fill from the opposite side: a Blinn-Phong highlight on the bezel normal, a hairline right at the edge that is brighter on the lit side, and a darker shadow side. The pane's own colour (`--wc`) tints the light by 30 %. |
| Fill | Blur by mip level (`--lg-blur` of the slider), saturation (`--lg-sat`), then the DOM tint on top. |

The numbers a slider value produces are `glassGl(v, dpr)`, a pure function that the tests run:

| | Matte (4 and below) | Default (60) | Liquid (100) |
|---|---|---|---|
| Pass | off | on | on |
| Bend (`refr`) | | 0.7 | 1.0 |
| Dispersion (`disp`) | | 0.67 | 1.0 |
| Blur (mip level at dpr 1.25) | | 4.5 (11 css px) | 3.3 (5 css px) |
| Saturation | | 1.9 | 2.4 |
| Edge light (`rim`) | | 0.5 | 0.9 |

### When the pass does not run, and what you see then

| Situation | Result |
|---|---|
| Frost or Flat step, or the slider at 4 and below | No pass; the panes are what they always were (frost, flat or matte). |
| Below the wide layout (1180 x 620) | No pass: the tiles are under the stage there, not over it. DOM frost. |
| No WebGL2, a software renderer (`failIfMajorPerformanceCaveat`), `aos.gl = "0"`, a lost context | No pass; DOM frost, and the small controls keep their SVG lens. |
| Reduced motion | The pass runs. The stage loop is off there, so the stage redraws for a second after a tile moves, a page turns or the slider changes (`touch`). |
| A window larger than the graphics card's texture limit (very large multi-monitor windows, old cards capped at 8192 px) | No pass; DOM frost. |
| A flight to Second brain or Atlas | The glass fades with the tiles (the same 0.3 s fade; its canvas has the class `hs-glass`). |

What the pass does not do: it bends the stage (galaxy, dust, ball glows), not the page's CSS background (the slow aurora discs and the square grid), which lies below the stage canvas and shows through unbent; both are soft, so the cost is not visible. Nor is it glass in glass: a control inside a pane is a flat inset, as before.

### Cost of the pass

Measured on one machine (an AMD GPU, 1446 x 732 at device pixel ratio 1.25, home page with the galaxy running, default slider, frames counted by `requestAnimationFrame` over 6 s after a reload): Frost 102 frames per second, the glass pass 87 and 90 (median frame 7.8 ms against 8.0 ms, 95th percentile 15.8 against 16.7 and 22.3 ms). A Chromium trace of the same two modes over 13 s agrees: 148 against 124 submitted frames per second, and the GPU process spent 4.1 s in GPU tasks with the pass against 3.5 s with frost. So the pass costs a little more than the DOM frost it replaces (about 12 to 15 % of the frames on this screen, which runs well above 60 Hz), and a good deal less than the SVG lens on large panes (14 to 16 ms per frame). This is one GPU and a few runs; other hardware will differ. The knobs for a slow machine are the slider itself (the matte end turns the pass off), the Frost step of the glass button, and `aos.gl = "0"`.

### Where a lens is not drawn

- **Inside another pane.** A backdrop filter sees the nearest *backdrop root* behind it, and every ancestor with `backdrop-filter`, `filter`, `opacity < 1`, a mask and so on is one. A control inside a card would only ever see the card, so inside panes controls are flat translucent insets by design, and popups that open inside a pane (`.mp-pop`, `.atl-recent-pop`, `.agx-box`) are nearly opaque. The Atlas view therefore shows no lensed piece; that is expected, not a bug.
- **Large panels.** Measured: an SVG lens on a dozen large widgets cost 14 to 16 ms per frame on top of the galaxy, so the SVG lens is only for small pieces. The widgets of the home page get their bend from the graphics card instead (next section); everywhere else large panes are frost only.
- **Off screen or smaller than 8 px.**
- **Over budget.** Pieces are served in priority order (tab bead, header buttons, chips and the search field, orbs, key figures) and then smallest first, until the budget of **150000 device px²** (chroma pieces count double) is used. `lgPlan` is the whole policy.

### Cost

Measured on one machine (Chromium, 1600 x 900, device pixel ratio 1, home view with the galaxy running, mean frame time over a few seconds):

| | flat | frost | lens, default budget | lens, unlimited |
|---|---|---|---|---|
| ms / frame | 27.0 | 29.2 | 31.3 | 30.0 |

The medians were equal (27.8 ms): the lens costs a little in the mean, not in the typical frame. This is one GPU, one display and one run; **other hardware will differ**, and a device pixel ratio of 2 spends the same budget on fewer pieces (cost scales with `dpr²`).

Knobs in `localStorage` (the first and the third have a control in the page; all of them can be set from the browser console):

| Key | Meaning |
|---|---|
| `aos.glass` | `lens`, `frost` or `flat`. Written by the header button. Remove it to follow the system again. |
| `aos.glassBudget` | Device px² of lens per screen. `0` means frost only. Ignored if it is not a number >= 0. |
| `aos.widgetGlass` | How see-through the widgets are, `0` (matte) to `100` (completely liquid); `60` is the look they had before it could be chosen. Written by the slider in the Customise menu. Anything that is not a number is the default. |
| `aos.gl` | `0` paints the galaxy with the 2D canvas instead of WebGL2 (see "The wallpaper") and turns the glass of the widgets off (DOM frost). Anything else, or nothing, uses the GPU where there is one. |

## Why the CSS looks the way it does

- **The block is last and every rule starts with `html:root body`.** That is specificity (0,2,2), above older rules like `body.is-home .card` (0,2,1), so the order of the file does not matter for the glass and the old rules stay as they were. `tests/test_design_system.py` counts them.
- **Entrances are opacity and transform only.** A filter (or a long-lived opacity below 1) makes the element its own backdrop root, and the glass inside it would show only itself while it enters. `lgRise`, `lgIn`, `lgInR` and the two side slides have no `filter`; a test enforces it.
- **Everything that moves sits in one `prefers-reduced-motion: no-preference` block.** Outside it there is no `@keyframes` and no `animation`; hover colours are transitions.
- **Atlas panes float inside their grid cells** with a margin instead of changing the grid, because the camera model (`atlasMapBox`) measures the map from the column widths.

## The homescreen

The home page is arranged like the home screen of a phone: the galaxy is the wallpaper (the stage fills the whole screen, so the stars run behind every tile), and the widgets are tiles of glass on a snap grid in a zone on each side of it. What does not fit goes to the next page. Everything below is `Section 8. View: Today` of the script.

### The model

The part that needs no DOM is one block (`// ---- homescreen model`, pure functions) and is the part that is tested under Node.

| Term | Meaning |
|---|---|
| Cell | About 68 px. `hsMetrics(W, H)` picks the number of columns `C` (8 to 40) and rows `R` (4 to 24) so that cells stay about the same size and the grid ends exactly one pad from the right edge and one dock (56 px) above the bottom. |
| Zone | `Z` columns (2 to 8) on each side of the galaxy; the rest of the width is the galaxy's. Widgets start in their zone, the galaxy keeps at least about 500 px. |
| Tile | `{ id, p, a, x, y, w, h }`: page, anchor (`l` or `r`: which edge `x` is counted from), position and size in cells. The anchor is what keeps a widget on its side of the screen when the window gets wider or narrower. |
| Page | A full set of cells. `hsResolve` lets no two tiles of one page overlap, pushes the others down and, when a page is full, onto the next. It is deterministic and idempotent (running it on its own output changes nothing), and the tile you are moving keeps the place you gave it. |
| Default | `hsPack` puts each widget, in the order of `WIDGETS`, at the first free place of its side: the left zone fills from the left edge, the right zone from the right edge. Widths are given for a zone of 6 columns and scale down for a narrower one (never below 2). |

Every widget has three sizes (`sizes`: S, M, L as `[columns, rows]`) and a default one. Until you change something nothing is stored: the default is worked out for the screen you have, so it always fits.

### Arranging

| How | What happens |
|---|---|
| Pencil in the header, or hold a widget for half a second | Arranging: tiles wobble, each gets a hide badge (`−`), S / M / L chips and a corner handle. Content does not react while you arrange. |
| Drag a tile | A dashed ghost shows the cell it lands in; the other tiles glide out of the way. Hold it at the left or right screen edge for 0.7 s and the page turns (beyond the last page there is one new page). |
| Drag the corner | Resizes in whole cells; the left edge stays. |
| Keyboard | Focus a tile: arrow keys move it one cell, Shift + arrow keys resize it, Delete hides it, PageUp / PageDown move it to another page. Each change is announced (`aria-live`). |
| Customise menu (grid icon) | The see-through slider, then a checkbox per widget: show or hide it; a widget that comes back takes the first free place on the page you are on. While arranging, the slider is also in the bar, next to Reset layout. |
| Reset layout | Back to the default for this screen. |

Below 1180 x 620 px there is no room for a grid: the tiles flow in columns under the stage and arranging is `↑` / `↓` and `−` per tile. That order is its own list (`flow`), so arranging a phone does not move the desktop.

### Widgets fit their tile

A tile can be anything from 2 x 2 cells up, so a widget is not drawn at one size. Two things work together:

- **Type and spacing follow the box.** Every tile is a size container (`container: tile / size`). The key figures, the clocks and the greeting scale with the tile (container units, clamped), and in steps (box heights of 330, 300, 260, 215, 205 and 150 px, widths of 300, 260 and 180 px) padding gets tighter and small print and decoration go: the sparkline of a key figure, the analogue clock, the sub line of the greeting, the zone of a time. Container units sit inside a container query on purpose: the flow layout has no tile container, and there they would mean the window.
- **Blocks and rows leave in order of importance.** What fits depends on the data (how many deadlines, which blocks exist), so a small script decides. `WIDGET_FIT` lists, per widget, its blocks with a rank (a higher rank leaves first; a part that is not listed never leaves). `fitTile` starts from nothing and brings blocks back from the most important, a list one row at a time, for as long as the body does not overflow. `fitPlan` is the pure part of that and is tested under Node. A list of rank 1 always keeps its first row, and a "+N more" line says what is not shown. A block you opened yourself (the time zones, the schedule) stays. It runs again when the box changes (resizing, another screen, late fonts, something opened). In the flow layout a tile is as tall as its content and nothing is trimmed.

Every widget has a minimum size (`min`, in cells; the four number tiles take 2 x 2); dragging the corner and the keyboard stop at it.

**Quick launch** (`launch`) is the widget that has no data of its own: one button per view (`VIEWS`, without Today, where you already are), each opened like its tab, because the home page has no tab bar. It is a grid that wraps, so it is not in `WIDGET_FIT`: names are shown only where the whole grid with names fits (a container query on the tile: from 350 px wide two rows of 62 px are needed, below that three; a short tile gets icons only, the name stays in the tooltip and the accessible label), and a tile that is smaller than its icons scrolls inside itself. It comes after the deadlines in `WIDGETS`, so on a short screen it sits under them rather than pushing the calendar away.

Because a small screen can push that tile to a later page, there is a second way to every view that no arrangement can move: the **Apps** button in the header (the grid-of-dots icon, next to the Customise menu) opens the same list of views as a menu. The default arrangement keeps the tile on page 1 at the screen sizes that were probed (1180 x 620 up to 1920 x 1080); the Health widget is what moves to page 2 on the larger ones. Once you have arranged tiles yourself, your saved arrangement wins.

### Saved arrangement

`localStorage` key `aos.widgets`, this browser only, never sent anywhere:

```
{ v: 5, hidden: [ids], tiles: { id: { p, a, x, y, w, h } } | null, flow: [ids] | null }
```

Every field is validated on load (unknown ids, negative numbers and repeated ids are dropped, a broken value gives the default). An older layout (`v` 4 and below: a list per column) is arranged once into tiles; what you hid yourself stays hidden. A tile saved on a large screen is fitted to a smaller one on load, so nothing can leave the screen.

### See-through

The stage is deep space with a faint nebula; the panes in it use more transparency than the dark theme (`--lg-a: 22%`, `--lg-blur: 11px`, `--lg-sat: 1.9`), so stars and colour show through. The colour behind the glass moves as three soft discs; they are plain radial gradients, not a 96 px blur filter, because the glass above has to re-sample whatever is behind it on every frame, and a big blur filter makes that expensive.

**How much** is yours to choose: the slider at the top of the Customise menu (and in the bar while arranging) goes from matte to completely liquid, one number from 0 to 100 for every widget. The look above is its default (60). Five tokens, and a text shadow, move along three stops with straight lines between them:

| | Matte (0) | The old look (60, default) | Liquid (100) |
|---|---|---|---|
| `--lg-a`, the share of its colour a pane keeps | 96 % | 22 % | 3 % |
| `--lg-blur` | 0 px | 11 px | 5 px |
| `--lg-sat` | 1 | 1.9 | 2.4 |
| `--lg-rim`, the lit edge | .18 | .5 | .9 |
| `--lg-sheen` | .03 | .13 | .24 |
| text shadow (`--hs-shade`) | none | none | .55 |

The blur peaks at the old look on purpose: clear glass shows the stars sharp, and the text shadow keeps type readable on a pane that is almost not there. At 4 and below the panes have no backdrop filter at all and are skipped by the lens, which is also the cheapest setting. Flat glass (the header button, or reduced transparency) wins: the panels stay opaque, the slider is disabled and says why. Double-click the slider, or press Default, to go back to 60. The value is `aos.widgetGlass`, this browser only; the tokens are set on the grid, so every widget inherits them and nothing else on the page changes.

### The wallpaper

The galaxy is a constant 11,700 particles (9000 stars, 1800 glow, 900 dust). Nothing thins it out: not time, not a long stay in Atlas, not a slow machine, so the mist and the nebula stay as they are. What keeps the frames smooth is the painter and a frame cap (about 75 fps; a stage that is hidden or scrolled out of view does no work), never fewer particles.

The cloud is painted by WebGL2 (`glxScene`: one instanced draw per pass over the same arrays the simulation steps, the sprites are the same canvases the 2D painter uses, glow and stars additive and the dust over them). The 2D painter (`drawCloudScene`) is the reference and the fallback: it paints exactly the same picture and takes over without WebGL2, on a software renderer (`failIfMajorPerformanceCaveat`), after a lost context, for a transform it cannot map, and with `aos.gl` = `0`. Measured once, on one AMD integrated GPU in Chrome: the canvas painter cost about 14 ms of script plus as much again in the GPU process per frame, the instanced draws well under 1 ms. Other hardware will differ.

### Motion

| Where | What | How |
|---|---|---|
| Tile moves to its cell | Glide with a small overshoot (`--lg-spring`) | CSS transition of `translate` |
| Tile is picked up | Lifts to 1.045 | `scale`, shadow |
| Tile is dropped, resized, or a size is chosen | Jelly: squash and stretch settling in about 0.8 s | `hsJelly` (`scale`, alternating X and Y) |
| Widget is shown / hidden | Pops in with an overshoot / shrinks away | `hsPopIn`, `.hs-pop` |
| Arranging | Tiles wobble by half a degree, each out of step | `hsJiggle` (`rotate`), `--n` delay |
| Page dots | The dot of the current page is a bead that widens on a spring | transition of `width` |
| Chips and the reset button | Appear as a drop: tall and thin, then squashed, then round | `hsDrop` |
| Tab bar | The bead stretches along its way and wobbles at the end | `translate` plus a Web Animation of `scale` |

Position is the `translate` property of a tile and effects are `scale` and `rotate`, so they compose without fighting over `transform` and an effect pivots on the tile itself. All CSS motion is in the `prefers-reduced-motion: no-preference` block; the scripted motion (jelly, the hide pop, smooth scrolling, the bead) asks `RM.matches` and with reduced motion things simply jump.

### Limits

- Tiles are a fixed size. A widget shows what fits (see "Widgets fit their tile"); what you open inside it (the model and effort matrix of a skill, the time zones editor) stays, and the content then scrolls inside the tile. The matrix is scrolled into view when it opens.
- A tile on another page is hidden, inert and skipped by the lens.
- On touch screens the hold-to-arrange gesture and the corner handle work; page turning at the edge is a pointer gesture, the dots are the alternative.
- Checked in one Chromium on one GPU only, at 1440 x 800: every widget at S, M, L and at its minimum (70 tile and size combinations: nothing sticks out sideways; two are one pixel taller than their box, which is the engine's tolerance), the slider (values, keyboard, persistence, Flat), and the galaxy painter against the canvas painter. The quick-launch tile came after that sweep: it was looked at by eye at 1442, 1282 and 902 px wide and is not one of those 70 combinations. Not checked: a real touch device, other browsers and GPUs, other screen sizes, a real mouse drag of the slider thumb, and the text shadow in the light theme.
- Not measured on real hardware: how it feels on a phone, and the frame cost of 17 tiles on a weak GPU (the quick-launch tile makes 18). In the Chromium used while developing this (WebGL2 on a real GPU, ANGLE / D3D11; frame times there are noisy, 20 to 30 ms around the galaxy alone) the three moving discs cost about 13 ms per frame as blurred elements and about 5 ms as gradients; other hardware will differ.

## Where the ideas come from

- **[callstack/liquid-glass](https://github.com/callstack/liquid-glass)** (MIT) is a React Native module that wraps Apple's iOS 26 glass effect. It is a native view and cannot run in a browser, so no code is shared. Its *vocabulary* is what this design follows, as far as it applies on the web: regular glass (every pane and control), `none` (the Flat step), `interactive` (pointer highlight and press), a tint per pane (`--lg-over`), containers (one pane whose children are drawn flat inside it), and support detection with a fallback (`lgMode`: Lens falls back to Frost, Frost to Flat). The library's `clear` variant is not used by any piece here.
- **[ybouane/liquidglass](https://github.com/ybouane/liquidglass)** is a web implementation (WebGL plus a DOM snapshot). It was evaluated and **not adopted**: it needs a script from a CDN or npm (the dashboard is one file that `aos serve` sends under `default-src 'none'`, standard library only), glass elements must be direct children of one root and cannot nest, it uses one WebGL context per element (browsers allow about 16 live ones, which is about the number of glass pieces on one screen here), and it renders from a snapshot of the DOM, which does not suit zoomed, scrolling columns over an animated canvas. Borrowed as ideas only: the chromatic dispersion, the lit rim, the pointer specular highlight and the press behaviour.
- The lens maths (signed distance of a rounded rectangle, power falloff in the rim, displacement by `feDisplacementMap`) is the common SVG technique for refraction in the browser, written from scratch for this file.
- **"Liquid Glass UI: Crafting a Droplet-Inspired Animation That Transforms Into a Toolbar"** (Sarvjeet Singh, Medium) is where the *motion* of the homescreen comes from: squash and stretch on a spring (alternating `scaleX` / `scaleY` keyframes), a drop-like pop-in, and distortion on press. Only the technique is used; the article's code is not copied (the script here moves position by `translate` and effects by `scale` / `rotate`).
- **Apple's Liquid Glass** (iOS 26 and macOS 26) is the look the whole glass work is aiming at. Apple has not published how it is drawn, so the glass of the widgets ("The glass of the widgets") follows what the community has worked out by looking at it: a convex squircle rim, refraction by Snell's law, a little colour dispersion, a lit hairline and a specular highlight that follows the pointer. It is written from scratch for this file; no Apple code, assets or names are used.
- **[thinking-orbs](https://github.com/Jakubantalik/thinking-orbs)** (Jakub Antalik, MIT) gave the idea of the dotted "thinking" indicators (the orbits, globe, constellation and wave of the small agent indicators). **ReactBits** and **Skiper UI** are collections of React components; the spotlight, magnet, counter and staggered reveal effects are known patterns from them. All of these are small, dependency-free implementations written for this file; no code was copied.
- **Uppbeat's "liquid glass animations"** is a catalogue of ready-made motion-graphics templates (finished animation files for video). There is no code to take from it; it was only a reference for how liquid glass should move.

## Changing it

- Colour or tint of all panes: the `--lg-*` tokens. Dark values are in three places (see above); a test counts them.
- A new control type: add its class to the controls selector list *and* to `LG_LENS` if it should get a lens; the contract test fails if a candidate has no glass rule that reads `--lg-f`.
- A new pane type: add it to the pane rule and, if it can contain controls, to the "flat inside a pane" list.
- Always check light and dark theme, Home, Atlas, Second brain and a page tab, phone width, and `Lens`, `Frost`, `Flat`.

## Tests

| File | What it pins |
|---|---|
| `tests/test_liquid_glass.py` | The model under Node: the displacement map (neutral inside, outward normals, mirror symmetry, monotone falloff), bezel and scale clamps, the budget plan (priority, boundary, dpr scaling), the mode matrix; and the script/CSS contract (properties, lens candidates, header button, storage keys, support detection, no HTML strings, no literal script tag). |
| `tests/test_design_system.py` | Nothing moves outside the no-preference block, every keyframe is used, entrances never blur, `--wc` is always a token, the primary button stays readable, one surface recipe for panes and controls, nested glass is flat, flat / reduced-transparency / no-backdrop-filter fallbacks, tokens in light and the three dark places. |
| `tests/test_glass_gl.py` | The glass of the widgets: what a slider value means for the shader (`glassGl`: monotone, matte is off, density shifts the mip level), the shape of the bend (`glassShift`: zero in the flat, about one bezel width at the edge, folds back, index 1 bends nothing), shader and model written with the same lines, the shader interfaces (varyings, uniforms, instance layout) and the wiring (drawn last, copy before cut, off for Frost, Flat, matte and narrow, the fallback path, the class on the grid, no DOM writes while layout is read). |
| `tests/test_homescreen.py` | The homescreen model under Node: metrics cover the screen and leave the galaxy its room, tiles sit on the edges with the gap, the anchor, widths per zone, `hsResolve` (120 random layouts: no overlap, in bounds, idempotent, independent of input order, the moved tile stays), page overflow, move and resize, slots against the edge of their side, the default arrangement on eight screen sizes, migration of old layouts, new widgets and smaller screens, the flow order; `fitPlan` (importance order, rows one at a time, a rank 1 list keeps a row, 600 random cases that never overflow and leave nothing that would still fit), `fitTile` on a stand-in DOM (a calendar at five box heights, a block opened by hand, the flow layout), `glassTokens` (the default is the old look, monotone from matte to liquid, rubbish is the default); and the contract: media threshold equals the script's, `translate` positioning, all motion in the no-preference block and the scripted motion asking `RM`, inert / hidden other pages, one versioned key, the fit table names real widgets and classes, container units only where the tile is the container, minimum sizes, the slider in the menu and the bar, `aos.widgetGlass` only through the store, Flat wins; the quick launch has a button for every view and keeps its icons below 1100 px, and the collapsed search is not wider than its box. |
| `tests/test_galaxy_transitions.py` | The galaxy under Node, stepped at a fixed dt: the camera, promotion and morph are continuous and every star comes back; the budget is constant (no governor, no floor) and the mist is the same after minutes, hours and days; the per-particle targets equal the orbits; and the painters against stubs of the canvas and of WebGL2: the passes and their order, the uploads, agents and the Second Brain colours, every reason to fall back (rotated transform, too large, lost context, `aos.gl`, no WebGL2, a shader that does not compile). |
| `tests/test_home.py`, `tests/test_osview.py`, `tests/test_atlas.py` | Home panes float with a gap and no hairlines, the saved layout is validated and migrated, arranging works by keyboard, the Second brain menu is a floating pane, the hooks the Atlas camera relies on are unchanged. |

What the tests cannot show: how the glass *looks*, and what it costs on your GPU. Look at it, and use `aos.glassBudget` if it is slow.
