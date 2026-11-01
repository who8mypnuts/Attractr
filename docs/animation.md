# Animation

## Model

A **Timeline** has a duration, fps, loop mode (`none`, `loop`, `pingpong`), optional
motion blur (sub-frame samples) and a set of **tracks**. Each track animates one dotted
property path of the render settings, e.g. `params.rho`, `camera.rotation`,
`camera.zoom`, `look.phase`, `look.gradient`, `quality.dt`, and holds **keyframes**
`(time, value, easing)`. Evaluating the timeline at time *t* returns complete render
settings: the *base* settings with every animated property replaced by its interpolated
value (floats lerp, the camera quaternion slerps, gradients blend stop-wise or by LUT
cross-fade, colours lerp).

Easing (applied from a key to the next): `linear`, `ease_in`, `ease_out`, `ease_in_out`,
`smooth`, `hold`, `bezier(x1,y1,x2,y2)`.

The timeline is stored in the project file (`animation` key) — see project_format.md.

## Timeline panel (View → Timeline, `T`)

* Transport: ⏮ ▶/⏸ ⏹ ⏭, time/frame read-out, duration, fps, loop mode.
* **◆ Key all / Params / Camera / Look** record the current document values at the
  playhead. Workflow: move the playhead, change things, press a Key button (or enable
  **Auto-key** to record every edit of an already-animated property).
* Scrubbing the ruler applies the interpolated state to the whole UI and the live preview.
* Right-click a track for *add key here* / *delete key* / *remove track*; select a key to
  change its easing.
* **Helpers ▾** build whole timelines: Turntable (yaw/pitch/roll, N revolutions, seamless
  loop), Morph A→B (capture A, change things, capture B), Parameter sweep (random target
  ±40 % of each range, ping-pong), Palette cycle, Zoom in, Orbit trace (one trajectory
  drawn progressively).

## Framing lock

Per-frame re-fitting would make the image "breathe" when parameters morph. With **Lock
framing** (default) the bounding sphere is computed at the key times (union of spheres)
and written into the camera (`lock_center`, `lock_radius`); every engine then uses that
fixed sphere.

## Rendering

**Animate → Render animation…** (or the button in the Timeline panel) opens the dialog:
size/quality tier/engine/supersampling, motion-blur samples, output folder + name,
resume (skip existing frames), encoder preset and CRF. The job renders
`<folder>/<name>/<name>_0001.png…`, writes `<name>_manifest.json` (settings, per-frame
timing/coverage) and `<name>_report.md`, then runs ffmpeg.

Encoder presets: H.264 MP4 (yuv420p, CRF), H.265/HEVC MP4, ProRes 422 HQ MOV, VP9
WebM, GIF (two-pass palette), or PNG frames only. ffmpeg is found on `PATH`, from
Preferences → *ffmpeg executable*, or from `imageio-ffmpeg` when installed.

CLI: `attractr animate project.attractr -o frames --fps 30 --size 1920x1080 --encode h264 --crf 18`.
