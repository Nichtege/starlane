# Design: the iOS 27 language and liquid glass

The dashboard speaks the visual language of Apple's iOS and iPadOS 27: the system colours, label levels and grouped backgrounds, the system font, the controls of the UI kit (switches, sliders, segmented controls, capsule buttons, a floating tab bar, menus, popovers and sheets) and Liquid Glass as the material of what floats. This page explains how that is built, what it costs, how it degrades, and how to change it. It is for contributors; the user-facing parts are one button in the header (**Lens / Frost / Flat**) and the Customise menu of the home page (see-through, accent colour, widgets).

Everything lives in `aos/web/dashboard.html`: section 1 of the style block (tokens and tints), the base and stage sections (components), the style block "Liquid glass" (last in `<style>`, on purpose) and the script sections "5c. Liquid glass" (`LG`) and the tint (`applyTint`). There is no build step and no dependency.

**Provenance.** The values come from Apple's "iOS and iPadOS 27" UI kit (the Figma Community file Apple publishes for designing apps) and from the Human Interface Guidelines: colours, sizes, radii, blur, saturation, refraction, dispersion and shadow, as numbers. No Apple asset is copied: no SF font (the page asks the system for its own font, which is SF Pro only on Apple devices), no SF Symbol (the icons are drawn here as strokes), no image, icon, wallpaper or component from the kit. Liquid Glass itself is reimplemented from what it looks like (see "The glass of the widgets"); no Apple code is used.

## The iOS 27 language

### Colour

| Role | Light | Dark | Notes |
|---|---|---|---|
| Background | `#f2f2f7` (grouped) | `#000000` | pages are grouped lists, as in Settings |
| Surface, raised surface | `#ffffff`, `#f2f2f7` | `#1c1c1e`, `#2c2c2e` | cards, insets |
| Labels | `#000`, then 85 % and 76 % of `rgba(60,60,67)` | `#fff`, then 70 % and 60 % of `rgba(235,235,245)` | the two secondary tones are a little stronger than Apple's 60 % so small print keeps 4.5:1 |
| Fills | the four system fills (`--fill-1` .. `--fill-4`) | the same, denser | buttons, fields, segmented tracks |
| Separators | `rgba(0,0,0,.12)` | `rgba(255,255,255,.17)` | |
| System colours | red `#ff383c`, orange `#ff8d28`, yellow `#ffcc00`, green `#34c759`, mint, teal, cyan, blue `#0088ff`, indigo `#6155f5`, purple, pink, brown, gray | the dark variants | categorical colours always come with a shape |
| Status | green, orange, red, each with an `-ink` shade for text and a `-bg` fill | | the ink keeps 4.5:1 on its own fill |

Home, Second brain and Atlas are the **stage**: deep space (`--void`) in every theme, so their tokens are the dark ones (`body.is-home, body.is-brain, body.is-atlas`).

### Accent colour (tint)

The accent is one of the nine tints of iOS: **blue** (default), purple, pink, red, orange, yellow, green, indigo, graphite. It is picked under **Accent colour** in the Appearance sheet or in the Customise menu of the home page (a radio group of swatches; arrow keys move the choice), set as `<html data-tint>` and stored in this browser only under `aos.tint`. Each tint is six tokens:

| Token | Use |
|---|---|
| `--tint-l`, `--tint-d` | the colour itself in light and dark: graphics, the slider fill, focus rings, selection washes |
| `--tint-ink`, `--tint-ink-d` | text and icons in the tint: 4.5:1 on white and on the grouped background, and on black, `#1c1c1e` and `#2c2c2e` |
| `--tint-btn`, `--tint-on` | a filled control with a label (primary button, the sent bubble in Atlas, a selected chip) and that label: 4.5:1 |

The roles the rest of the stylesheet uses are `--accent` (graphics), `--accent-ink` (text), `--accent-btn` + `--on-accent` (labelled fills) and `--accent-soft` (a selection wash). Yellow and orange carry a black label, as on iOS; their text shades are dark olive and brown. `tests/test_ios_design.py` recomputes every one of these contrasts.

Instead of a tint the Appearance sheet also takes an **own colour** (`accent` in `aos.look`). `lookAccent` makes the six tokens from it with the same contrasts: the colour itself for graphics; for text a shade of it at 4.5:1 on `#f2f2f7` and on `#2c2c2e`; for a labelled fill the colour with a white label, else a black one, else a darker shade of it with a white label, always at 4.5:1. They are written over the tint's tokens, so everything that uses the accent follows at once. Picking a swatch ends an own colour; `tests/test_appearance.py` checks the contrasts for pale, dark, grey and saturated colours.

### Type

The system font (`system-ui`: SF Pro on Apple devices, Segoe UI on Windows, Roboto on Android), the rounded design for big numbers (`ui-rounded`, SF Pro Rounded where it exists) and the system monospace only for code and paths. Sizes are the iPadOS text styles (large title 34, title 28 / 22 / 20, headline 17 semibold, body 17, subheadline 15, footnote 13, caption 12 / 11), as tokens `--t-*`. Labels are in sentence case; there are no uppercase or letter-spaced labels. Nothing is downloaded or embedded, so the page CSP has no `font-src`.

### Components

| Component | As in the kit | Here |
|---|---|---|
| Switch | 64 x 28 capsule, white 38 x 24 knob, green when on | every on/off checkbox (`role="switch"`); the knob stretches while pressed; forced colours get the native checkbox; `prefers-contrast: more` adds the on/off glyphs |
| Slider | 6 px track filled in the tint, white 38 x 24 knob | `.hs-glass-range`, `.os-range`, the effort slider; the fill follows the knob through `--f`, set by `rangeFill()` |
| Segmented control | 32 px capsule track, the selected segment white (light) or 27 % white (dark) | `--seg-on`; Second brain layouts, Atlas filters |
| Button | capsule; glass in a toolbar, a fill inside content, the tint for the primary action | `.btn`, `.icon-btn`, `.os-btn`, `.os-ibtn`, chips |
| Tab bar | a floating glass capsule with a bead under the selected tab | sticky at the top of the page tabs, so it stays in reach while you scroll |
| Menu, popover | glass, radius 34; on a phone (720 px and less) the menus are a bottom sheet instead, since a 320 px menu anchored to a button mid-screen would run off the edge | the Customise and Apps menus, search results, the inspector |
| Sheet | radius 38 on a phone (a bottom sheet with a grabber), 32 for a form sheet | the detail inspector at phone width, the agent editor |
| App icon | a squircle with a colour per app and a white glyph | Quick launch and the Apps menu: one colour per view (`.app-ico[data-app]`), continuous corners where `corner-shape: squircle` exists; every colour keeps 3:1 with the glyph |
| Messages | sent bubble in the tint with a small tail corner, received bubble grey | the conversation of Atlas |
| Home screen | widgets with their title in the widget's colour, page dots, jiggle mode with a minus badge | the homescreen (below) |

### Where glass is used

Glass is the **navigation layer**: the tab bar, the toolbar buttons, menus, popovers, sheets and hover cards, on every tab; plus the widgets that float over the galaxy (home) and the panes of Second brain and Atlas. The cards of a page tab (Skills, Timeline, Health, ...) are **solid** grouped surfaces, as content is on iOS: glass on a plain background would only cost frames and contrast.

## The three steps

| Mode | What you see | Needs |
|---|---|---|
| **Lens** | Frosted glass plus real refraction at the rim: what lies behind a piece bends at its edge (small pieces also split the colours a little). The widgets of the home page are painted by the graphics card ("The glass of the widgets" below); small controls get an SVG lens. | WebGL2 for the widgets (every current browser), a Chromium based browser for the small controls (Chrome, Edge, Opera, Brave, ...). |
| **Frost** | Backdrop blur, saturation, a lit top edge, a hairline, a soft drop. No refraction. | `backdrop-filter`. |
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
| Pane (stage only) | `.card`, `.kpi`, `.deadline`, `.ag-card`, hero | 28 px (`--lg-r`), small ones 22 px | frost, lit rim, hairline, the drop of the kit (`0 8 48`) |
| Control | `.btn`, `.icon-btn`, `.os-ibtn`, `.os-btn`, `.hs-atlas`, `.chip`, search field | capsule / disc | lighter tint, a highlight that follows the pointer, swells on press |
| Tab bar | `.tabs` with the bead `.tab-ind` | capsule | the bead is the lens |
| Popup | `.detail`, `.results`, `.w-pop`, `.hs-card`, `.os-card`, `.os-preview`, `.os-controls`, `.os-legendbox`, `.tip`, `.note`, `.os-help` | 34 px menus (`--lg-r-menu`), 38 px sheets (`--lg-r-sheet`), 28 / 22 px panes | denser tint (`--lg-a-pop`) so text never depends on what is behind it |
| Inset | tiles, rows, fields inside a pane | 12 px (`--lg-r-s`) and up | a system fill, no backdrop of their own |

Tokens (light in the glass block's `:root`, dark values in the three dark places: explicit dark theme, system dark, and the stage, which is dark in every theme):

```
--lg-r 28px  --lg-r-m 22px  --lg-r-s 12px  --lg-gap 16px  --lg-r-menu 34px  --lg-r-sheet 38px
--lg-blur 16px  --lg-sat 1.8
--lg-a / --lg-a-pop / --lg-a-ctl   how much of the surface colour a pane / popup / control keeps (light 72 / 84 / 64 %)
--lg-rim  --lg-sheen              lit edge, strength of the sheen
--lg-hair  --lg-drop              the hairline round a piece (#a6a6a6 at 34 % in dark) and its drop shadow (.16 light, .45 dark)
--lg-over                         tint of one pane (amber / red deadlines, error / ok notes)
--wc                              colour of one widget (accent, cyan, violet, pink); always a token, never a literal
```

## The lens

A lens is an SVG filter used as a backdrop filter: `backdrop-filter: url(#lgN) blur(...) saturate(...)`.

1. `lgLensMap(w, h, r, bezel)` computes a displacement map from the signed distance of the rounded rectangle. Inside the shape and beyond the rim the pixel is neutral grey (128). In the rim the red and green channels lean along the outward normal, strongest at the very edge (`(1 - t)^2`, `t` = depth / bezel).
2. The map becomes a 24-bit BMP `data:` URL (`lgBmpUrl`, written byte by byte; the page CSP allows `img-src data:`), used by `feImage`, and `feDisplacementMap` shifts the backdrop with it. BMP is uncompressed, so it holds exactly the same pixels a PNG would, without the encoder: drawing a canvas and `toDataURL` took about 130 ms of the page load.
3. Pieces up to 9000 css px² also get **chromatic dispersion**: three displacement passes (scale x1, x0.92, x0.84), one per colour channel, added back with two `feBlend screen`.
4. The filter is built in the element's own, unscaled pixels (`offsetWidth`, not the bounding box): a tile that is lifted while you drag it, or wobbles after a drop, is scaled by CSS and the filter must not be rebuilt for that.
5. Filters are cached by size and radius (LRU, 160 entries), so twenty chips of the same width share one.

The engine sets exactly three custom properties on a lensed element (`--lg-f`, `--lg-bc`, `--lg-blur`) and removes them again; the CSS reads them with fallbacks, which is why frost is simply "the lens variable is empty". `tests/test_liquid_glass.py` checks both sides against each other.

## The glass of the widgets

On the home page the tiles are over the galaxy, which is where a refracting pane is worth having, and they are as big as a window: an SVG lens would cost more than the whole stage. So there the glass is painted by the graphics card, in one pass (`createGlassPass`, a WebGL2 canvas laid over the stage canvas and under the tiles):

1. The stage is painted as usual (galaxy, dust, ball glows) into its 2D canvas.
2. That canvas is copied into a texture and its mip levels are generated. The mip levels are the blur: a sample at level 5 is a smooth blur about as wide as the 16 px of the kit, for the price of one texture read.
3. The stage canvas is cut open under every visible tile (`destination-out`, rounded rectangles), so the unbent picture does not show through.
4. Every tile is drawn once as a rounded rectangle that shows the texture, bent at the edge, saturated and lit. Edge anti-aliasing and the tile's current opacity (a tile that fades out takes its glass with it) are part of the same pass.

The pane in the DOM keeps its tint, hairline and text and has **no backdrop filter** while the pass runs (`.hs-grid.hs-glx`); its own lit top edge is dropped (`--lg-rim: transparent`) because the pass draws one all the way round.

### How the bend works (what the look is made of)

Apple has not published how Liquid Glass is drawn; the following is the community's reverse engineering of what it looks like, and this is a reimplementation of that idea, not Apple's code. The strengths at the default are the ones the iOS 27 kit gives its regular glass (refraction .7, dispersion .2, frost 16).

| Part | Here |
|---|---|
| Shape | The pane is a rounded rectangle (signed distance field). Its rim, the **bezel** (`glassBezel`: 0.9 of the corner radius, at most 0.3 of the short side and 30 css px), is the only part that bends light; inside it the glass is flat. |
| Profile | The bezel is a convex "squircle": height `y = (1 - (1 - x)^4)^(1/4)` with `x` the depth into the rim. It is vertical at the very edge and flat inside. |
| Bend | The slope gives the angle at which a ray from the eye meets the surface. **Snell's law** for glass of index 1.5 turns it into a shift (`glassShift`): about one bezel width at the edge, nothing in the flat. The ray came from further inside, so the rim shows the interior folded back, as a glass bead does. |
| Dispersion | Red, green and blue are bent by slightly different amounts (up to 14 % of the shift), only inside the rim. |
| Light | A key light from the upper left (it follows the pointer a little) and a weaker fill from the opposite side: a Blinn-Phong highlight on the bezel normal, a hairline right at the edge that is brighter on the lit side, and a darker shadow side. The pane's own colour (`--wc`) tints the light by 30 %. |
| Fill | Blur by mip level (`--lg-blur` of the slider), saturation (`--lg-sat`), then the DOM tint on top. |

The numbers a slider value produces are `glassGl(v, dpr)`, a pure function that the tests run; refraction and dispersion are stops of `GLASS_STOPS` like everything else:

| | Matte (4 and below) | Default (60) | Liquid (100) |
|---|---|---|---|
| Pass | off | on | on |
| Bend (`refr`) | | 0.7 | 1.0 |
| Dispersion (`disp`) | | 0.2 | 1.0 |
| Blur (mip level at dpr 1.25) | | 5.0 (16 css px) | 3.6 (6 css px) |
| Saturation | | 1.8 | 2.4 |
| Edge light (`rim`) | | 0.3 | 0.6 |

### When the pass does not run, and what you see then

| Situation | Result |
|---|---|
| Frost or Flat step, or the slider at 4 and below | No pass; the panes are what they always were (frost, flat or matte). |
| Below the wide layout (1180 x 620) | No pass: the tiles are under the stage there, not over it. DOM frost. |
| No WebGL2, a software renderer (`failIfMajorPerformanceCaveat`), `aos.gl = "0"`, a lost context | No pass; DOM frost, and the small controls keep their SVG lens. |
| Reduced motion | The pass runs. The stage loop is off there, so the stage redraws for a second after a tile moves, a page turns or the slider changes (`touch`). |
| A window larger than the graphics card's texture limit (very large multi-monitor windows, old cards capped at 8192 px) | No pass; DOM frost. |
| A flight to Second brain or Atlas | The glass fades with the tiles (the same 0.3 s fade; its canvas has the class `hs-glass`). |

What the pass does not do: it bends the stage (galaxy, dust, ball glows), not the page's CSS background (the slow aurora discs and the faint nebula), which lies below the stage canvas and shows through unbent; both are soft, so the cost is not visible. Nor is it glass in glass: a control inside a pane is a flat fill.

### Cost of the pass

Measured on one machine, with the earlier, lighter default (11 px blur; the kit's 16 px is one mip level coarser, which costs the same texture reads): an AMD GPU, 1446 x 732 at device pixel ratio 1.25, home page with the galaxy running, default slider, frames counted by `requestAnimationFrame` over 6 s after a reload: Frost 102 frames per second, the glass pass 87 and 90 (median frame 7.8 ms against 8.0 ms, 95th percentile 15.8 against 16.7 and 22.3 ms). A Chromium trace of the same two modes over 13 s agrees: 148 against 124 submitted frames per second, and the GPU process spent 4.1 s in GPU tasks with the pass against 3.5 s with frost. So the pass costs a little more than the DOM frost it replaces (about 12 to 15 % of the frames on this screen, which runs well above 60 Hz), and a good deal less than the SVG lens on large panes (14 to 16 ms per frame). This is one GPU and a few runs; other hardware will differ. The knobs for a slow machine are the slider itself (the matte end turns the pass off), the Frost step of the glass button, and `aos.gl = "0"`.

### Where a lens is not drawn

- **Inside another pane.** A backdrop filter sees the nearest *backdrop root* behind it, and every ancestor with `backdrop-filter`, `filter`, `opacity < 1`, a mask and so on is one. A control inside a card would only ever see the card, so inside panes controls are flat fills by design, and popups that open inside a pane (`.mp-pop`, `.atl-recent-pop`, `.agx-box`) are opaque. The Atlas view therefore shows no lensed piece; that is expected, not a bug.
- **On a piece that is drawn flat.** The cards of a page tab and anything else whose computed `backdrop-filter` is `none` get no lens: there is nothing behind them to bend.
- **Large panels.** Measured: an SVG lens on a dozen large widgets cost 14 to 16 ms per frame on top of the galaxy, so the SVG lens is only for small pieces. The widgets of the home page get their bend from the graphics card instead (previous section); everywhere else large panes are frost only.
- **Off screen or smaller than 8 px.**
- **Over budget.** Pieces are served in priority order (tab bead, header buttons, chips and the search field, orbs, key figures) and then smallest first, until the budget of **150000 device px²** (chroma pieces count double) is used. `lgPlan` is the whole policy.

### Cost

Measured on one machine (Chromium, 1600 x 900, device pixel ratio 1, home view with the galaxy running, mean frame time over a few seconds):

| | flat | frost | lens, default budget | lens, unlimited |
|---|---|---|---|---|
| ms / frame | 27.0 | 29.2 | 31.3 | 30.0 |

The medians were equal (27.8 ms): the lens costs a little in the mean, not in the typical frame. This is one GPU, one display and one run; **other hardware will differ**, and a device pixel ratio of 2 spends the same budget on fewer pieces (cost scales with `dpr²`).

Knobs in `localStorage` (all but the second and the last have a control in the page; all of them can be set from the browser console):

| Key | Meaning |
|---|---|
| `aos.glass` | `lens`, `frost` or `flat`. Written by the header button. Remove it to follow the system again. |
| `aos.glassBudget` | Device px² of lens per screen. `0` means frost only. Ignored if it is not a number >= 0. |
| `aos.widgetGlass` | How see-through the widgets are, `0` (matte) to `100` (completely liquid); `60` is the regular glass of the kit. Written by the slider in the Customise menu. Anything that is not a number is the default. |
| `aos.tint` | The accent colour: `blue` (default), `purple`, `pink`, `red`, `orange`, `yellow`, `green`, `indigo` or `graphite`. Written by the swatches (the Customise menu and the Appearance sheet). Anything else is blue. |
| `aos.look` | The Appearance sheet: `{ form, stars: [8 colours], dust, backdrop, sky, glow: [3 colours], icons, iconTint, ball, accent }`, colours as `#rrggbb` (`accent` is empty unless an own accent colour is laid over `aos.tint`). Empty (or missing) for the standard look. A field that is not valid is the standard. |
| `aos.gl` | `0` paints the galaxy with the 2D canvas instead of WebGL2 (see "The wallpaper") and turns the glass of the widgets off (DOM frost). Anything else, or nothing, uses the GPU where there is one. |

## Why the CSS looks the way it does

- **The glass block is last and every rule starts with `html:root body`.** That is specificity (0,2,2), above older rules like `body.is-home .card` (0,2,1), so the order of the file does not matter for the glass and the base rules stay simple. `tests/test_design_system.py` counts them.
- **Page cards are solid, stage panes are glass.** The pane recipe is `html:root body:not(.is-page) :is(.card, ...)`; the tab bar, buttons and popups are glass on every tab.
- **Entrances are opacity and transform only.** A filter (or a long-lived opacity below 1) makes the element its own backdrop root, and the glass inside it would show only itself while it enters. `lgRise`, `lgIn`, `lgInR` and the two side slides have no `filter`; a test enforces it.
- **Everything that moves sits in one `prefers-reduced-motion: no-preference` block.** Outside it there is no `@keyframes` and no `animation`; hover colours are transitions.
- **Atlas panes float inside their grid cells** with a margin instead of changing the grid, because the camera model (`atlasMapBox`) measures the map from the column widths. Their lists fade out under the edge of the pane instead of being cut, as the scroll edge of iOS 27 does.

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
| Pencil in the header, or hold a widget for half a second | Arranging, as in the jiggle mode of iOS: tiles wobble, each gets a minus badge (`−`), S / M / L chips and a corner handle. Content does not react while you arrange. |
| Drag a tile | A soft shadow shows the cell it lands in; the other tiles glide out of the way. Hold it at the left or right screen edge for 0.7 s and the page turns (beyond the last page there is one new page). |
| Drag the corner | Resizes in whole cells; the left edge stays. |
| Keyboard | Focus a tile: arrow keys move it one cell, Shift + arrow keys resize it, Delete hides it, PageUp / PageDown move it to another page. Each change is announced (`aria-live`). |
| Customise menu (grid icon) | The see-through slider, the accent colour, then a switch per widget: show or hide it; a widget that comes back takes the first free place on the page you are on. While arranging, the slider is also in the bar, next to Reset layout. |
| Reset layout | Back to the default for this screen. |

Below 1180 x 620 px there is no room for a grid: the tiles flow in columns under the stage and arranging is `↑` / `↓` and `−` per tile. That order is its own list (`flow`), so arranging a phone does not move the desktop.

### Widgets fit their tile

A tile can be anything from 2 x 2 cells up, so a widget is not drawn at one size. Two things work together:

- **Type and spacing follow the box.** Every tile is a size container (`container: tile / size`). The key figures, the clocks and the greeting scale with the tile (container units, clamped), and in steps (box heights of 330, 300, 260, 215, 205 and 150 px, widths of 300, 260 and 180 px) padding gets tighter and small print and decoration go: the sparkline of a key figure, the analogue clock, the sub line of the greeting, the zone of a time. Container units sit inside a container query on purpose: the flow layout has no tile container, and there they would mean the window.
- **Blocks and rows leave in order of importance.** What fits depends on the data (how many deadlines, which blocks exist), so a small script decides. `WIDGET_FIT` lists, per widget, its blocks with a rank (a higher rank leaves first; a part that is not listed never leaves). `fitTile` starts from nothing and brings blocks back from the most important, a list one row at a time, for as long as the body does not overflow. `fitPlan` is the pure part of that and is tested under Node. A list of rank 1 always keeps its first row, and a "+N more" line says what is not shown. A block you opened yourself (the time zones, the schedule) stays. It runs again when the box changes (resizing, another screen, late fonts, something opened). In the flow layout a tile is as tall as its content and nothing is trimmed.

Every widget has a minimum size (`min`, in cells; the four number tiles take 2 x 2); dragging the corner and the keyboard stop at it.

**Quick launch** (`launch`) is the widget that has no data of its own: one app icon per view (`VIEWS`, without Today, where you already are), each opened like its tab, because the home page has no tab bar. It is a grid that wraps, so it is not in `WIDGET_FIT`: names are shown only where the whole grid with names fits (a container query on the tile: from 350 px wide two rows of 62 px are needed, below that three; a short tile gets icons only, the name stays in the tooltip and the accessible label), and a tile that is smaller than its icons scrolls inside itself. It comes after the deadlines in `WIDGETS`, so on a short screen it sits under them rather than pushing the calendar away.

Because a small screen can push that tile to a later page, there is a second way to every view that no arrangement can move: the **Apps** button in the header (the grid-of-dots icon, next to the Customise menu) opens the same list of views as a menu. The default arrangement keeps the tile on page 1 at the screen sizes that were probed (1180 x 620 up to 1920 x 1080); the Health widget is what moves to page 2 on the larger ones. Once you have arranged tiles yourself, your saved arrangement wins.

### Saved arrangement

`localStorage` key `aos.widgets`, this browser only, never sent anywhere:

```
{ v: 5, hidden: [ids], tiles: { id: { p, a, x, y, w, h } } | null, flow: [ids] | null }
```

Every field is validated on load (unknown ids, negative numbers and repeated ids are dropped, a broken value gives the default). An older layout (`v` 4 and below: a list per column) is arranged once into tiles; what you hid yourself stays hidden. A tile saved on a large screen is fitted to a smaller one on load, so nothing can leave the screen.

### See-through

The stage is deep space with a faint nebula; the panes in it use more transparency than the dark theme (`--lg-a: 40%`, `--lg-blur: 16px`, `--lg-sat: 1.8`), so stars and colour show through. The colour behind the glass moves as three soft discs; they are plain radial gradients, not a 96 px blur filter, because the glass above has to re-sample whatever is behind it on every frame, and a big blur filter makes that expensive.

**How much** is yours to choose: the slider at the top of the Customise menu (and in the bar while arranging) goes from matte to completely liquid, one number from 0 to 100 for every widget. The default (60) is the regular glass of the kit. Seven values, and a text shadow, move along three stops with straight lines between them (`GLASS_STOPS`):

| | Matte (0) | Default (60), the kit | Liquid (100) |
|---|---|---|---|
| `--lg-a`, the share of its colour a pane keeps | 96 % | 40 % | 6 % |
| `--lg-blur` | 0 px | 16 px | 6 px |
| `--lg-sat` | 1 | 1.8 | 2.4 |
| `--lg-rim`, the lit edge | .12 | .3 | .6 |
| `--lg-sheen` | .02 | .06 | .16 |
| refraction (`refr`, the pass) | .3 | .7 | 1 |
| dispersion (`disp`, the pass) | .05 | .2 | 1 |
| text shadow (`--hs-shade`) | none | none | .55 |

The blur peaks at the default on purpose: clear glass shows the stars sharp, and the text shadow keeps type readable on a pane that is almost not there. At 4 and below the panes have no backdrop filter at all and are skipped by the lens, which is also the cheapest setting. Flat glass (the header button, or reduced transparency) wins: the panels stay opaque, the slider is disabled and says why. Double-click the slider, or press Default, to go back to 60. The value is `aos.widgetGlass`, this browser only; the tokens are set on the grid, so every widget inherits them and nothing else on the page changes.

### The wallpaper

The galaxy is a constant 11,700 particles (9000 stars, 1800 glow, 900 dust). Nothing thins it out: not time, not a long stay in Atlas, not a slow machine, so the mist and the nebula stay as they are. What keeps the frames smooth is the painter and a frame cap (about 75 fps; a stage that is hidden or scrolled out of view does no work), never fewer particles.

The cloud is painted by WebGL2 (`glxScene`: one instanced draw per pass over the same arrays the simulation steps, the sprites are the same canvases the 2D painter uses, glow and stars additive and the dust over them). The 2D painter (`drawCloudScene`) is the reference and the fallback: it paints exactly the same picture and takes over without WebGL2, on a software renderer (`failIfMajorPerformanceCaveat`), after a lost context, for a transform it cannot map, and with `aos.gl` = `0`. Measured once, on one AMD integrated GPU in Chrome: the canvas painter cost about 14 ms of script plus as much again in the GPU process per frame, the instanced draws well under 1 ms. Other hardware will differ.

### Appearance

**Customise → Appearance**, or **Appearance** in the bar while arranging (the pen; as Customize in the edit mode of iOS), opens a sheet (a floating pane beside the galaxy, a bottom sheet on a phone) with six parts. Each part has its own **Standard**, and **Back to the standard look** at the bottom resets all of them at once (the accent back to blue). Every change shows at once, while the sheet is open.

- **Galaxy**: the form of the cloud, twenty-one with a small preview of each, under two headings. Galaxies: **Spiral** (the barred Milky Way, the standard), **Swirl** (a grand-design spiral: two long open arms, no bar), **Whirlpool** (a grand-design spiral whose outer arm runs out to its small yellow companion, with a bridge of stars and a dust lane across the companion), **Ring** (a small core and a bright ring of young stars), **Cartwheel** (a blue rim of star birth with pink knots, an inner ring round the core, spokes between and a small companion), **Elliptical** (a smooth, flattened ball of old warm light), **Sombrero** (a great bulge and a thin disc seen almost edge-on, the dark lane of its rim in front), **Antennae** (two spirals in collision, young knots where they meet, two tidal tails in an S) and **Irregular** (an off-centre bar in a lopsided disc and a great pink nebula, like the Large Magellanic Cloud) and **Cluster** (a giant elliptical among smaller ellipticals and spirals, each spiral at its own tilt, in the faint light between them). Beyond them: **Cloud** (a nebula of soft coloured lumps), **Hourglass** (a planetary nebula: two lobes blown out along an axis, filaments on their walls, pinched by a ring of dust round the white dwarf), **Black hole** (a thin accretion disc turning fast inside round a dark shadow, its photon ring and the far side of the disc bent over the top), **Supernova** (a shell torn into filaments, the blue edge of its shock and a pulsar sweeping its beams round), **Quasar** (a blinding core, a hot disc in a torus of dust and two knotted jets ending in lobes), **Comet** (a green coma, the straight blue ion tail and the broad curved dust tail with its striae, still against the stars), **Planet** (a banded globe, rings with the Cassini division, the Encke gap and the F ring, two moons), **Solar system** (the Sun, eight planets on faint orbits turning as Kepler has it, Saturn's ring, the asteroid and Kuiper belts), **Atom** (protons and neutrons, three leaning electron orbits with their electrons), **Helix** (a double helix turning about its axis) and **Wormhole** (a grid of rings and spokes falling into a funnel, its glowing throat and the mouth of the other side, light spiralling in). What must face the viewer (the black hole's shadow, ring and bent light; the Sombrero, whose dust lane may only lie in front; the comet) turns at exactly minus the turn of the whole cloud (`HOME_SPIN`), so it stands still while the rest moves. Switching does not rebuild anything: the 11,700 particles get new targets and the same spring physics that flies them to Atlas carries them into the new shape. Every form keeps the particles' roles, sizes and brightness in the spiral's ranges, and every 24th star (a cluster star) outside the centre, so the painters, the flights and the agents of Atlas work unchanged in every form.
- **Colours**: seven palettes (**Milky Way**, the standard, then Ember, Ice, Aurora, Neon, Gold and Silver) and a well for each of the galaxy's eight colours (core, old, warm, pale and young stars, clusters, nebulae, rim) plus the dust. A colour the current form hardly uses is dimmed. The sprites are repainted in place; the GPU painter uploads those 17 cells of its atlas once and the palette of the small stars follows.
- **Backdrop**: what fills deep space behind Home, Atlas and the Second brain, with a preview of each: **Quiet** (the standard: the few tiny stars of `--space`, nothing added), **Starfield** (many faint stars in true colours, a few bright ones with the four spikes of a telescope, three loose clusters), **Deep field** (hundreds of small distant galaxies: ellipticals, spirals at every tilt and edge-on ones with their dark lane, the farthest reddened), **Milky Way** (the band of our galaxy across the window, warmer towards its centre, a river of faint stars, dark rifts and a few pink nebulae), **Nebulae** (four clouds of glowing gas in the colours of the glows, torn by dark lanes, young stars in them), **Constellations** (figures between brighter stars, as on a star chart) and **Shooting stars** (the starfield, and a meteor every few seconds). It is painted once into one canvas in `.bg` (`paintBackdrop`, seeded and laid out in shares of the window) when the look or the size of the window changes: nothing of it is redrawn per frame. It shows in the space views only (`.bg-sky`), never on the pages of the light theme. A shooting star is one element moved by a CSS animation inside the `prefers-reduced-motion: no-preference` block; none start for reduced motion, in a hidden tab or outside the space views.
- **Sky and scenery**: the sky (the page behind Home, Atlas and the Second brain, and the deep space of every stage and flight) and the three glows (the moving discs behind the widgets and the matching glows of the nebula in `--space`). A sky light enough to leave white text under 4.5:1 gets a warning in the sheet.
- **Accent colour**: the nine tints or an own colour, for every button, link, highlight, chosen item and focus ring at once (the primary buttons such as Ask Atlas, the words of the greeting, the logo; see Accent colour above). Its Standard is blue.
- **Icons**: the four icon looks of iOS (**Default**, **Dark**, **Clear**, **Tinted**; `html[data-icons]`). Tinted uses the accent colour unless you pick an icon colour. The same part sets the colour of the balls (skills and artifacts) on the home page.

The look is `aos.look` (JSON). A changed look is a few custom properties with `!important` in one `<style id="aos-look">`, and the **standard look writes no style and stores nothing**, and the quiet backdrop has no canvas: the page is then exactly what it is without the feature (the standard spiral is pinned bit for bit by a test, and the `--space` the sheet writes uses the same legacy `rgba()` gradients as the CSS, because `color-mix()` renders them up to 2/255 differently). Everything stored is validated on load: an unknown form is the spiral, an unknown backdrop the quiet one, and anything that is not `#rrggbb` is the standard colour, so nothing but a hex colour ever reaches the CSS.

Cost, measured once in the Chromium used while developing this: every form paints at the same frame time as the spiral (the GPU painter re-uploads the particle codes once per change of form, nothing per frame). Choosing a form costs about 20 to 50 ms once (building the new targets; the spiral itself is in that range); opening the sheet about 12 ms. A colour that is dragged is applied once per frame, not once per input event, and repaints only its own two sprites; the 28 previews are drawn a few per frame (at most 4 ms of them in a frame; the first sight of a form builds its 2400 stars) and follow about eight times a second while dragging and at once otherwise. A backdrop paints in 3 to 11 ms once (1536 x 674 at 1.25x; the Milky Way is the dearest) into a canvas of at most 8 megapixels (the device pixel ratio gives way first), and again 200 ms after the window stops changing size; the nebulae follow a dragged glow 150 ms after it rests. The sky and the glows are custom properties at the root, so dragging one restyles the page once per frame (about 19 ms here); a galaxy colour does not touch the CSS at all.

### Motion

| Where | What | How |
|---|---|---|
| Tile moves to its cell | Glide with a small overshoot (`--lg-spring`) | CSS transition of `translate` |
| Tile is picked up | Lifts to 1.045 | `scale`, shadow |
| Tile is dropped, resized, or a size is chosen | Jelly: squash and stretch settling in about 0.8 s | `hsJelly` (`scale`, alternating X and Y) |
| Widget is shown / hidden | Pops in with an overshoot / shrinks away | `hsPopIn`, `.hs-pop` |
| Arranging | Tiles wobble by half a degree, each out of step | `hsJiggle` (`rotate`), `--n` delay |
| Page dots | Equal dots; the current one is opaque | transition of `background` |
| Chips and the reset button | Appear as a drop: tall and thin, then squashed, then round | `hsDrop` |
| A glass control is pressed | It swells a little and lights up under the pointer, then settles on a spring | `scale`, `--lg-spot` |
| Switch | The knob slides on a spring and stretches while held | `translate`, `width` |
| Tab bar | The bead stretches along its way and wobbles at the end | `translate` plus a Web Animation of `scale` |

Position is the `translate` property of a tile and effects are `scale` and `rotate`, so they compose without fighting over `transform` and an effect pivots on the tile itself. All CSS motion of the glass is in the `prefers-reduced-motion: no-preference` block; the scripted motion (jelly, the hide pop, smooth scrolling, the bead) asks `RM.matches` and with reduced motion things simply jump.

### Limits

- Tiles are a fixed size. A widget shows what fits (see "Widgets fit their tile"); what you open inside it (the model and effort matrix of a skill, the time zones editor) stays, and the content then scrolls inside the tile. The matrix is scrolled into view when it opens.
- A tile on another page is hidden, inert and skipped by the lens.
- On touch screens the hold-to-arrange gesture and the corner handle work; page turning at the edge is a pointer gesture, the dots are the alternative.
- The accent colour is chosen on the home page only (the Customise menu); it applies everywhere.
- Checked in one Chromium on one GPU only. The homescreen sweep (every widget at S, M, L and at its minimum, 70 tile and size combinations, at 1440 x 800) was made before the iOS 27 values; the iOS 27 pass was looked at by eye in light and dark, at desktop and phone width, in all three glass steps and with several tints. Not checked: a real touch device, other browsers and GPUs, and Firefox's rendering of the switch knob (a pseudo-element on a checkbox with `appearance: none`).
- Not measured on real hardware: how it feels on a phone, and the frame cost of 17 tiles on a weak GPU (the quick-launch tile makes 18). In the Chromium used while developing this (WebGL2 on a real GPU, ANGLE / D3D11; frame times there are noisy, 20 to 30 ms around the galaxy alone) the three moving discs cost about 13 ms per frame as blurred elements and about 5 ms as gradients; other hardware will differ.

## Frame and load cost

An optimisation pass after the iOS 27 work, with the rule that no pixel may change. Measured in one Chromium on one machine (AMD GPU, 1804 x 842, a 144 Hz display, home page with the galaxy and the glass pass, 95th percentile of `requestAnimationFrame` intervals over several seconds); other hardware will differ.

| What | Why it cost | Now |
|---|---|---|
| The aurora discs | Three CSS drift animations moved every frame, and every glass surface above them was redone each time. | Each animation is paused when it starts and moved on ten times a second by `driftAurora` (under a px per step on a soft disc). The CSS keeps the curve; reduced motion turns them off. |
| The glass pass | It read the tile rectangles after the frame had moved the bubbles, so each frame forced a layout. | `glass.measure()` reads first, at the top of the frame; `render` uses those numbers. |
| The Atlas button | Its satellites turned as an SVG, which Chromium restyles every frame. | They turn in an HTML box, which runs on the compositor. |
| Lens maps | PNG through a canvas (see "The lens"). | BMP written directly. |

Home page with the lens: frame p95 from about 15 ms to 8.2 to 8.5 ms (a 144 Hz frame is 6.9 ms); Atlas, Second brain and Skills about 8.2 ms. Load: main-thread time in the first 5 s of a traced reload went from 3.57 s to 3.00 s; first contentful paint was the same within the noise of the machine (500 to 1000 ms run to run either way). Not changed, and why: most of the first long task is the first layout of the page (one-time font and style set-up, about 190 ms), which any first paint pays; the fit of the widgets (about 65 small layouts, 80 ms) could probe with a binary search, but the "+N more" line makes the height not quite monotone in the rows, so it could choose a different row count than today.

## Where the ideas come from

- **Apple's iOS and iPadOS 27 UI kit** (the Figma Community file Apple publishes) and the **Human Interface Guidelines** are the source of the language: the system colours and their dark variants, the label, fill and separator levels, the grouped backgrounds, the text styles, the sizes of the switch (64 x 28, knob 38 x 24), the slider (6 px track, knob 38 x 24) and the segmented control (32 px), the radii of menus (34), popovers and sheets (38) and widgets, and the parameters of regular Liquid Glass (refraction .7, dispersion .2, frost 16, light fill white at 70 %, dark `#1a1a1a` at 70 to 90 %, shadow `0 8 48` at .25 / .45, hairlines). Only these numbers are used. No Apple asset is part of this repository: no SF Pro, SF Mono or SF Symbols, no icon, image, wallpaper or component of the kit. The look follows Apple's design language; the project is not affiliated with or endorsed by Apple.
- **[callstack/liquid-glass](https://github.com/callstack/liquid-glass)** (MIT) is a React Native module that wraps Apple's glass effect. It is a native view and cannot run in a browser, so no code is shared. Its *vocabulary* is what this design follows, as far as it applies on the web: regular glass (every pane and control), `none` (the Flat step), `interactive` (pointer highlight and press), a tint per pane (`--lg-over`), containers (one pane whose children are drawn flat inside it), and support detection with a fallback (`lgMode`: Lens falls back to Frost, Frost to Flat). The library's `clear` variant is not used by any piece here.
- **[ybouane/liquidglass](https://github.com/ybouane/liquidglass)** is a web implementation (WebGL plus a DOM snapshot). It was evaluated and **not adopted**: it needs a script from a CDN or npm (the dashboard is one file that `aos serve` sends under `default-src 'none'`, standard library only), glass elements must be direct children of one root and cannot nest, it uses one WebGL context per element (browsers allow about 16 live ones, which is about the number of glass pieces on one screen here), and it renders from a snapshot of the DOM, which does not suit zoomed, scrolling columns over an animated canvas. Borrowed as ideas only: the chromatic dispersion, the lit rim, the pointer specular highlight and the press behaviour.
- The lens maths (signed distance of a rounded rectangle, power falloff in the rim, displacement by `feDisplacementMap`) is the common SVG technique for refraction in the browser, written from scratch for this file.
- **"Liquid Glass UI: Crafting a Droplet-Inspired Animation That Transforms Into a Toolbar"** (Sarvjeet Singh, Medium) is where the *motion* of the homescreen comes from: squash and stretch on a spring (alternating `scaleX` / `scaleY` keyframes), a drop-like pop-in, and distortion on press. Only the technique is used; the article's code is not copied (the script here moves position by `translate` and effects by `scale` / `rotate`).
- **Apple's Liquid Glass** (iOS 26 and 27, macOS 26) is the look the whole glass work is aiming at. Apple has not published how it is drawn, so the glass of the widgets ("The glass of the widgets") follows what the community has worked out by looking at it: a convex squircle rim, refraction by Snell's law, a little colour dispersion, a lit hairline and a specular highlight that follows the pointer. It is written from scratch for this file; no Apple code or assets are used.
- **[thinking-orbs](https://github.com/Jakubantalik/thinking-orbs)** (Jakub Antalik, MIT) gave the idea of the dotted "thinking" indicators (the orbits, globe, constellation and wave of the small agent indicators). **ReactBits** and **Skiper UI** are collections of React components; the spotlight, magnet, counter and staggered reveal effects are known patterns from them. All of these are small, dependency-free implementations written for this file; no code was copied.
- **Uppbeat's "liquid glass animations"** is a catalogue of ready-made motion-graphics templates (finished animation files for video). There is no code to take from it; it was only a reference for how liquid glass should move.

## Changing it

- A colour: the tokens of section 1. Dark values are in three places (explicit dark, system dark, the stage); a test counts them, and `tests/test_ios_design.py` fails if a label, status text or tint loses its contrast.
- A tint: a `:root[data-tint="…"]` rule with all six tokens, a swatch (`.w-tint[data-tint="…"]`) and an entry in `TINTS`; the test recomputes its contrasts and checks that the three lists agree.
- A new view: give its app icon a colour (`.app-ico[data-app="…"]`, dark enough for 3:1 with white); the test fails until it has one.
- Colour or tint of all glass: the `--lg-*` tokens.
- A new control type: add its class to the controls selector list *and* to `LG_LENS` if it should get a lens; the contract test fails if a candidate has no glass rule that reads `--lg-f`.
- A form of the galaxy: a branch in `galaxyFormPoint` (same roles and ranges, cluster stars at r >= 0.4, enough stars of size 1.1 and more for the agents; `cam` places what must face the viewer), its name in `GALAXY_FORMS` (in the order of the sheet, the galaxies first: `LOOK_FORM_GROUPS`) and `LOOK_FORM_NAMES`; `tests/test_appearance.py` checks it is a whole galaxy with room for 40 agents. A palette: a row in `LOOK_PRESETS`. A backdrop: its id in `LOOK_BACKDROPS` and `LOOK_BACKDROP_NAMES` and a branch in `paintBackdrop`; the test paints it on a counting context.
- A new pane type: add it to the pane rule and, if it can contain controls, to the "flat inside a pane" list.
- Always check light and dark theme, Home, Atlas, Second brain and a page tab, phone width, `Lens`, `Frost`, `Flat`, and at least one tint besides blue (yellow is the hardest).

## Tests

| File | What it pins |
|---|---|
| `tests/test_ios_design.py` | The iOS 27 language: the nine tints with all their tokens, wired to the accent roles, the same in CSS, swatches and script; every tint, label and status contrast recomputed (translucent labels composited over white, grouped, black, `#1c1c1e` and `#2c2c2e`); a colour for every app icon with 3:1 for the glyph; every checkbox a switch of the kit's size; sliders that fill their track; the radii of menus, sheets and widgets; the floating tab bar; system fonts, rounded numerals, no uppercase labels, mono only for code and paths; the glass stops at the kit's values, its hairline and drop; solid page cards; the tint picker as a radio group stored in `aos.tint`, nine swatches on one row; the provenance note; and the layout bugs the visual pass found (an empty artifact count that pushed the list down, the Rings hub label measured against its hexagon, the compact Atlas rail on a phone, menus as a bottom sheet over the corner buttons); the optimisation pass (the aurora stepped ten times a second and off with reduced motion, the glass pass reading layout before the frame writes, the Atlas orbit in an HTML box). |
| `tests/test_liquid_glass.py` | The model under Node: the displacement map (neutral inside, outward normals, mirror symmetry, monotone falloff), bezel and scale clamps, the budget plan (priority, boundary, dpr scaling), the mode matrix, the BMP of a map decoded back to the same pixels; and the script/CSS contract (properties, lens candidates, header button, storage keys, support detection, no HTML strings, no literal script tag). |
| `tests/test_design_system.py` | Nothing moves outside the no-preference block, every keyframe is used, entrances never blur, `--wc` is always a token, the primary button is an opaque tint fill, one surface recipe for panes and controls (lit rim, hairline, drop), nested glass is flat, flat / reduced-transparency / no-backdrop-filter fallbacks, tokens in light and the three dark places. |
| `tests/test_glass_gl.py` | The glass of the widgets: what a slider value means for the shader (`glassGl`: monotone, matte is off, density shifts the mip level), the shape of the bend (`glassShift`: zero in the flat, about one bezel width at the edge, folds back, index 1 bends nothing), shader and model written with the same lines, the shader interfaces (varyings, uniforms, instance layout) and the wiring (drawn last, copy before cut, off for Frost, Flat, matte and narrow, the fallback path, the class on the grid, no DOM writes while layout is read). |
| `tests/test_homescreen.py` | The homescreen model under Node: metrics cover the screen and leave the galaxy its room, tiles sit on the edges with the gap, the anchor, widths per zone, `hsResolve` (120 random layouts: no overlap, in bounds, idempotent, independent of input order, the moved tile stays), page overflow, move and resize, slots against the edge of their side, the default arrangement on eight screen sizes, migration of old layouts, new widgets and smaller screens, the flow order; `fitPlan` (importance order, rows one at a time, a rank 1 list keeps a row, 600 random cases that never overflow and leave nothing that would still fit), `fitTile` on a stand-in DOM (a calendar at five box heights, a block opened by hand, the flow layout), `glassTokens` (the default is the kit's glass, monotone from matte to liquid, rubbish is the default); and the contract: media threshold equals the script's, `translate` positioning, all motion in the no-preference block and the scripted motion asking `RM`, inert / hidden other pages, one versioned key, the fit table names real widgets and classes, container units only where the tile is the container, minimum sizes, the slider in the menu and the bar, `aos.widgetGlass` only through the store, Flat wins; the quick launch has a button for every view and keeps its icons below 1100 px, and the collapsed search is not wider than its box; the corner buttons of the home page are circles of one size (40 px, 44 px under a finger). |
| `tests/test_galaxy_transitions.py` | The galaxy under Node, stepped at a fixed dt: the camera, promotion and morph are continuous and every star comes back; the budget is constant (no governor, no floor) and the mist is the same after minutes, hours and days; the per-particle targets equal the orbits; and the painters against stubs of the canvas and of WebGL2: the passes and their order, the uploads, agents and the Second Brain colours, every reason to fall back (rotated transform, too large, lost context, `aos.gl`, no WebGL2, a shader that does not compile). |
| `tests/test_appearance.py` | The Appearance sheet: the spiral bit for bit as before the forms existed; every form under Node (seeded, roles at their indices, inside the unit ball, valid fields, cluster stars outside the centre, 40 agents for Atlas, really different shapes); the standard look writes no CSS and stores nothing; rubbish in `aos.look` becomes a valid look and only `#rrggbb` reaches the CSS; a changed sky, glow, ball or icon tint writes only itself, and the `--space` it writes equals the CSS one character for character; the palettes; the backdrop is a validated choice that writes no CSS, and every backdrop paints a seeded sky in one bounded paint with valid colours and alphas, its preview too; the black hole keeps its shadow empty and dark and its photon ring facing the viewer while the disc turns; the pen's Appearance button; the GPU painter re-uploads the particle codes on a new form and the 17 sprite cells and the palette on new colours, and nothing while the look stays; the menu entry, the restore at start and the icon CSS; the backdrop shows in the space views only, its shooting stars move only without reduced motion and outside the aurora's 10 Hz timer; an own accent is a whole tint at 4.5:1 for any colour and a swatch ends it; the ring of balls starts below the measured title and bar. |
| `tests/test_home.py`, `tests/test_osview.py`, `tests/test_atlas.py` | Home panes float with a gap, the saved layout is validated and migrated, arranging works by keyboard, the Second brain menu is a floating pane, the hooks the Atlas camera relies on are unchanged. |
| `tests/test_frontend.py` | One self-contained file: no external URL, system fonts only (no `@font-face`, no font files, no `font-src` in the CSP). |

What the tests cannot show: how the glass *looks*, and what it costs on your GPU. Look at it, and use `aos.glassBudget` if it is slow.
