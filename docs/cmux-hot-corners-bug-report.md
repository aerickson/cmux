# cmux leaves macOS window-drag state active, disabling Mission Control hot corners until cmux exits

## Environment

- cmux 0.64.22 (build 102), bundle `com.cmuxterm.app`
- macOS 26.6.2 (25G83), Apple M4 Pro
- cmux process had been running for approximately 15 days
- All four macOS hot corners configured for Mission Control

## Symptom

All Mission Control hot corners stop working globally. Dock remains responsive and receives every corner entry, but logs this for each attempt:

```text
hotcorners: handling mouse enter action 2
[com.apple.dock:missioncontrol] Unable to change mode from 0 to 1, in window drag. ssd: false, dwcs: true
```

Seventeen consecutive attempts produced the same result during a 20-second live capture.

## Controlled recovery test

1. Confirmed the bad state with cmux PID 1500 running and Dock PID 92299.
2. Quit cmux normally; did not restart Dock.
3. cmux completed termination at 12:54:21.463 PDT and launchd recorded exit(0) at 12:54:21.517.
4. Retried hot corners at 12:54:24.170 and 12:54:24.888.
5. Mission Control worked immediately. Dock remained PID 92299, continuously running since 12:12:05.
6. A fresh cmux process launched later at 12:54:45.

This confirms the failure was tied to stale state associated with the old cmux process. Exiting that process cleared macOS/Dock's `in window drag` state without a Dock restart.

## Suspected area

This matches upstream issue [#9713](https://github.com/manaflow-ai/cmux/issues/9713), which reproduces on cmux 0.64.22 by dragging a workspace entry in the sidebar: Mission Control/Space switching and cross-Space Dock activation then stop working until `killall Dock`.

The upstream fix, [PR #9807](https://github.com/manaflow-ai/cmux/pull/9807) (`Fix sidebar reorder breaking Mission Control`), was merged to `main` on 2026-08-12. It replaces the table's native drag-destination handling with a dedicated reorder overlay and explicitly resets reorder lifecycle state. Upstream validated Mission Control and cross-Space Dock activation after real workspace reorder operations. As of 2026-09-03, the latest stable release is still 0.64.22 and predates this fix; the fix is available in NIGHTLY.

This release contains custom/native window-drag paths and symbols including:

- `WindowDragHandleView`
- `performWindowDragWithEvent:`
- `draggingTab` / `activeDragTab`
- `SidebarWorkspaceDragRegistry`

Issue [#9521](https://github.com/manaflow-ai/cmux/issues/9521) describes several sticky drag-state latches in exactly cmux 0.64.22 build 102, including cleanup paths that can miss mouse-up/cancel when a drag ends outside the app or during window/view teardown. Issue [#400](https://github.com/manaflow-ai/cmux/issues/400) also documents a cross-window panel drag remaining stuck after mouse-up.

The most likely initiating interaction is reordering a cmux workspace in the sidebar. Other interrupted drag paths remain possible but are not needed to explain the observed failure.

## Expected behavior

Every completed, cancelled, or interrupted cmux drag clears both cmux-local state and any AppKit/window-system drag state. cmux must not leave Mission Control disabled globally.

## Actual behavior

Dock sees `dwcs: true` indefinitely and refuses Mission Control until the offending cmux process exits (or Dock itself is restarted).

## Attachments

- `Dock-broken-corner-attempts-2026-09-03-124748.sample.txt`
- `WindowManager-broken-corner-attempts-2026-09-03-124748.sample.txt`
- `broken-corner-attempts-2026-09-03-124748.log.txt`
- `cmux-sample-2026-09-03.txt`
- `post-quit-causal-test.txt`
