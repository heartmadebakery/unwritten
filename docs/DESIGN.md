# Design language — "Hearth"

The three apps (web, Android, iOS) share one design language and one
feature set. They do **not** share pixels: each draws the language in
its own platform's idiom, so it feels at home there. This file is the
spec; the app READMEs say how each platform draws it.

The brief (user-ordered Nov 2): friendlier and more approachable,
taking cues from Airbnb (warm whites, photo-first cards, big rounded
shapes, calm type) and the old Path app (a warm red accent, playful
round buttons, a personal greeting), with functionality kept in
parity across all three.

## Principles

1. **Warm, not dark.** Light warm paper by default; a matching dark
   palette follows the system setting on every platform. The camera
   viewfinder and full-screen players stay black — they are video.
2. **One warm accent.** *Ember* is the brand colour. It marks the one
   primary action on a screen (Record, Play) and nothing decorative.
3. **Big, round, touchable.** Tiles and cards with generous radii,
   pill buttons, 48 px/dp (44 pt on iOS) touch targets everywhere.
4. **Pictures before words.** A lesson is shown by its picture:
   device sessions by a frame of the video, hub lessons by a warm
   cover tile with the lesson's initial.
5. **Say it plainly, say it kindly.** Statuses are words in chips
   ("Uploading 42%", "In the cloud"), not glyph codes; empty states
   explain what will appear and how.

## Tokens

### Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| canvas | `#FAF6F1` | `#171310` | page background |
| surface | `#FFFFFF` | `#221C18` | cards, tiles, lists |
| sunken | `#F3ECE4` | `#2D2621` | inputs, pressed, tonal buttons |
| ink | `#2A211C` | `#F7EFE6` | primary text |
| ink2 | `#6F625A` | `#B9AA9C` | secondary text, icons |
| line | `#EADFD3` | `#3A312A` | hairlines, dividers |
| ring | `#DCCFC2` | `#5A4E44` | the shutter ring |
| ember | `#D2452A` | `#D2452A` | primary fill (white text ≥ 4.5:1) |
| emberInk | `#B83A20` | `#FF8A6B` | accent text, links, back |
| emberSoft | `#FCE8E1` | `#3A2420` | accent chips, tile wash |
| sage / sageSoft | `#2F7A4B` / `#E3F2E7` | `#7FD39B` / `#1F2E24` | Cloud on, "In the cloud" |
| honey / honeySoft | `#8A5A00` / `#FFF3D6` | `#F2C46B` / `#33281A` | "Preparing", quiet-mic notice |
| danger | `#C23B22` | `#C23B22` | no-microphone banner, delete |

Every text/background pair above meets WCAG AA (4.5:1) in its mode.

**Cover tiles** (hub lessons, and device rows with no frame yet) pick
one of six warm pairs by a stable hash of the title, letter on wash:

| Light wash / letter | Dark wash / letter |
|---|---|
| `#FCE3D9` / `#B5432A` | `#3A2420` / `#FF9C82` |
| `#FBEFD2` / `#8A5A00` | `#33281A` / `#F2C46B` |
| `#E2EFE1` / `#2F6B3F` | `#1F2E24` / `#7FD39B` |
| `#DDEBF4` / `#2B5F80` | `#1C2A33` / `#8CC4E6` |
| `#ECE3F3` / `#6A4486` | `#2B2233` / `#C7A6E0` |
| `#F2E3D8` / `#8A4F2E` | `#33251C` / `#E0A884` |

The hash is the same everywhere: sum of the title's UTF-16 code units
modulo 6, so a lesson wears the same colour on every platform.

### Type

Platform system faces (no web fonts — the PWA works offline and from
`file://`). Headings use the rounded variant where the platform has
one (SF Pro Rounded on Apple, `ui-rounded` on the web).

| Role | Size | Weight |
|---|---|---|
| Greeting eyebrow | 15 | semibold, ink2 |
| Large title | 32–34 | bold, rounded |
| Title (detail) | 24 | bold, rounded |
| Section header | 20 | bold, rounded, sentence case |
| Headline (row/tile title) | 17 | semibold |
| Body | 16 | regular, 1.5 line height for write-ups |
| Callout / subtitle | 14–15 | regular, ink2 |
| Chip | 13 | semibold |

Section headers are sentence case ("Hub", "This device") — not the
all-caps grey labels of the previous palette.

### Shape, depth, motion

- Radii: action tiles 24, cards 20, viewfinder 24, cover tiles and
  thumbnails 14, inputs 14, buttons and chips fully rounded (pill).
- Depth (light): cards float on a soft two-layer warm shadow
  (`0 1px 2px` at 6 % and `0 8px 24px` at 6 % of ink). Dark: no
  shadow; surface is lighter than canvas instead. Android uses real
  elevation (2 dp cards, 6 dp tiles); iOS uses a soft shadow.
- Motion: 180 ms ease-out. Tiles and the shutter dip to 96 % while
  pressed (a gentle Path-like squish). Reduced motion turns it off.
- Haptics where the platform has them: Record and Stop tap the
  phone (iOS sensory feedback, Android haptic constants).

## Components

- **Greeting** — "Good morning / afternoon / evening" eyebrow over
  the large title "Unwritten Craft", then the line "Record, upload,
  and revisit craft lessons."
- **Action tiles** — two side-by-side tiles on home. *Record* is
  filled ember with a white record glyph ("Film a lesson, the way
  you'd teach anyway"); *Upload video* is a surface tile with an
  ember-wash glyph ("From your phone or a link"). On Android and iOS
  the paste-a-link field sits under them in its own card; the web
  keeps its Upload page.
- **Lesson card (hub)** — cover tile (initial) + title (headline) +
  date (callout) + chevron. Tapping opens the lesson.
- **Session card (this device)** — 56 px video frame with the
  duration on it, the date as title, a status chip, and round icon
  buttons for Save a copy (↓) and Share link (↗). Tap plays;
  long-press (or swipe on iOS) deletes.
- **Status chips** — `On this device` (sunken), `Uploading 42%`
  (emberSoft), `Preparing` (honeySoft), `In the cloud` (sageSoft),
  `Upload failed · Retry` (emberSoft, tappable), `Ignored` (sunken),
  `Not saved yet` (honeySoft, web memory-only takes).
- **Lesson detail** — a cover banner (wash + big initial), title,
  date, an ember **Play** pill, round **Share** and **Delete**
  buttons, the write-up in comfortable body type, corrections as
  quote cards (time chip + the mentor's words in quotes + "Correcting
  …" underneath), and chapters as a time-chip list.
- **Viewfinder** — black, radius 24, a red-dot REC pill with the
  timer. Zoom sits below it in a pill track (− slider + label).
- **Shutter dock** — the round shutter (ring + ember disc, a rounded
  square while recording) centred in a surface card with the status
  line under it. Its accessible label stays "● Record" / "■ Stop
  m:ss", the shared contract.
- **Cloud card** — cloud glyph on a sage wash when on (sunken when
  off), "Cloud" + "Upload a copy for streamed playback", a real
  switch tinted sage.
- **Banners** — no microphone: danger fill, white text. Quiet for a
  minute: honeySoft with honey text.
- **Empty states** — a glyph in an ember-wash circle, a short title,
  and one line of help ("Sessions you record or upload appear
  here.").

## Per platform

| | Web (PWA) | Android | iOS |
|---|---|---|---|
| Light/dark | `prefers-color-scheme` | `Theme.DeviceDefault.DayNight` + runtime palette | dynamic `UIColor` palette |
| Navigation | large title on home, translucent top bar with back chevron | ActionBar with Up; system Back | `NavigationStack`, large rounded title, edge swipe |
| Lists | CSS cards | ripple rows in elevated cards | inset-grouped `List`, swipe + context menus |
| Icons | inline SVG, rounded strokes | programmatic line glyphs (`Glyphs.java`) | SF Symbols |
| Settings | inline panel | themed dialog | sheet with a `Form` |
| Upload | its own page (file + link) | system picker from the tile; link card on home | Photos/Files menu from the tile; link card on home |
| Feedback | press squish, focus rings | ripple, elevation, haptics, toasts | haptics, symbol effects, pull to refresh |
