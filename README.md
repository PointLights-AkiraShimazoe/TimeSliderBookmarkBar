# Time Slider Bookmark Bar

A Maya tool that shows **Time Slider Bookmarks as always-on colored bars** (with name and
frame range) right on the Time Slider, and lets you add / rename / recolor / move / resize /
delete bookmarks and drive the playback range from a small dockable UI.

Maya標準の Time Slider Bookmark を、タイムスライダー上に **色帯＋名前＋レンジで常時表示**し、
追加・リネーム・色変更・移動・範囲変更・削除・再配色・タイムレンジ操作までを
ドッキング可能なコンパクトUIから行えるツールです。

---

## Features

- Always-on colored **bars** on the Time Slider (name + range). Overlapping bookmarks stack into lanes.
- Dockable **control UI** (Maya `workspaceControl`): bar show/off, range show/off, and vertical sliders
  for bar size (dual handle = top/bottom), font size, alpha.
- **Add** bookmarks (Name / Start / End / Color), **rename + recolor**, **drag to move**, **drag edges to resize**.
- **Delete mode** (click a bar to delete) and **randomize all colors** (adjacent bookmarks get different colors).
- **Ctrl / Shift + click** on a bar to set the timeline St/Ed from neighbor/whole bookmark ranges.
- Settings **persist across Maya restarts** (`optionVar`).
- **Dock layout persists**: the docked position, the tab grouping, and *which tab was last open*
  (Bar Control / Color) are remembered by Maya's workspace and restored on the next launch.
- Maya 2020+ / PySide2 / PySide6.

---

## Install (drag & drop) — recommended

1. **Download** the latest release (Code → Download ZIP, or a Releases zip) and **unzip it anywhere**
   (a temp folder or Downloads is fine).
2. In Maya, **drag `install.py` into the viewport**.
3. Click **Install**. A shelf button (`BMBar`) is added.
4. Click the shelf button to launch.

> The installer **copies** the tool into your Maya user folder
> (`…/maya/modules/TimeSliderBookmarkBar/`), so it is self-contained.
> **After installing you can delete the unzipped folder and the ZIP** — the tool keeps working.

<sub>日本語: ZIPをどこでも良いので解凍 → `install.py` を Maya のビューポートにドラッグ＆ドロップ → [Install] → 追加されたシェルフボタンで起動。インストーラがツールを Maya のユーザーフォルダ（`…/maya/modules/TimeSliderBookmarkBar/`）へ**コピー**して自己完結するため、**インストール後は解凍フォルダも ZIP も削除して構いません**。</sub>

### What the installer does
- **Copies** `scripts/` and `icons/` into `…/maya/modules/TimeSliderBookmarkBar/`.
- Creates a Maya **module** file `…/maya/modules/TimeSliderBookmarkBar.mod` that points to that copied
  location (so it works on every launch, independent of where you unzipped).
- Adds a **shelf button** that runs `tsbl.show_controls()`.

---

## Install (manual)

Copy `scripts/timeslider_bookmark_labels.py` into any folder on your Maya script path
(e.g. `…/Documents/maya/scripts`), then run in the Script Editor (Python):

```python
import timeslider_bookmark_labels as tsbl
tsbl.show_controls()
```

---

## Usage

Launch with the shelf button, or `import timeslider_bookmark_labels as tsbl; tsbl.show_controls()`.

The UI has two Maya dock tabs: **バーコントロール (Bar Control)** and **カラー (Color)**.

Bar Control tab (left → right): bar On/Off, bar-size dual slider (top/bottom handles = bar top /
bottom position), font-size slider, alpha slider, range On/Off, and on the right a **＋** (add) with
a **−** (delete mode) below it.

### Bar (on the Time Slider) operations
- **Short single click** — rename + change color (popup opens just above the bar).
- **Drag center** — move the bookmark (keeps its length).
- **Double click** — set the timeline St/Ed to that bookmark's range.
- **Drag left/right edge** — change start / end frame (the grabbed edge is highlighted).
- **Ctrl + hover → click** `◀ ● ▶` — set St/Ed to the previous / all-bookmarks / next range.
- **Shift + hover → click** `◁ ▷` — set only Start to the previous bookmark's Start / only End to the next bookmark's End.
- **Delete mode** (− button ON, glows red): click a bar to delete it.

### Add / Color
- **＋** opens a compact popup with **Color / Name / Start / End** and ✕ / ◯ buttons.
- The **Color tab** has a rainbow bookmark button that **randomizes all bookmark colors** so that
  time-adjacent bookmarks are never the same color.

### Alignment (`inset`)
The bars are aligned to the frame ticks with a small pixel inset (default **12 px**, tuned on Maya 2027).
If your Maya version drifts symmetrically (matches at center, off toward the edges), adjust it live:

```python
tsbl.set_inset(12)      # both sides; increase/decrease until the edges line up
```

The value is saved and reused on the next launch.

### Dock position / active tab
Once you dock the UI where you like it, Maya remembers the position, the tab grouping, and which
tab (Bar Control / Color) was last active — the next launch restores that layout automatically, so
you don't have to re-dock each time. If Maya's workspace restore ever misbehaves, launch without
persistence, or run the diagnostic:

```python
tsbl.show_controls(persist=False)   # floating, no layout memory
tsbl.debug_persist()                # print persistence state for troubleshooting
```

---

## Uninstall

- Delete the folder `…/Documents/maya/modules/TimeSliderBookmarkBar/`.
- Delete `…/Documents/maya/modules/TimeSliderBookmarkBar.mod`.
- Remove the `BMBar` shelf button (middle-click drag to the trash, or edit the shelf).

---

## Requirements

- Autodesk Maya **2020 or later** (Time Slider Bookmarks required).
- PySide2 (Maya 2020–2024) or PySide6 (Maya 2025+) — both supported.

## License

[MIT](LICENSE) © 2026 Akira Shimazoe / PointLights for entertainment
