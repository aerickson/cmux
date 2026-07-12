# cmux Slowness Debugging

This runbook is for debugging a user report that the macOS cmux app feels slow,
high-CPU, laggy while typing, slow to switch workspaces, slow to scroll, or gets
worse after running for a long time.

The goal is to collect evidence before guessing. A good report should usually
include:

- one `sample` while cmux is slow
- one lightweight memory capture while cmux is slow
- whether restarting cmux fixes the issue
- the same captures after restart, if the restart changes behavior
- the number of open windows, workspaces, terminal panes, browser panes, and how
  long the app had been running

## Quick Capture

First reproduce the slow behavior. Capture while cmux is actively slow, not
after it has recovered.

From the repo checkout:

```bash
scripts/sample-cmux.py
```

The helper finds live cmux app processes and runs macOS `sample` when exactly one
cmux app process exists. By default it writes to:

```text
~/Desktop/cmux-samples/
```

If multiple cmux apps are running, list them and choose the one that is slow:

```bash
scripts/sample-cmux.py --list
scripts/sample-cmux.py --pid <pid>
```

For a longer capture:

```bash
scripts/sample-cmux.py --duration 30
```

If macOS denies access, rerun the printed `sudo sample ...` command.

## Memory Capture

Capture lightweight memory diagnostics for the same PID:

```bash
scripts/capture-memory.sh --pid <pid> --out ~/Desktop/cmux-memory-<pid>
```

The default capture is intentionally safe for a primary terminal-hosting cmux
instance. It records:

- `ps`
- `footprint -summary`
- `vmmap -summary`

Do not start with `--heavy` on a user's active cmux instance. `leaks` and
`malloc_history` can freeze a busy process. Use heavy heap tools only on a fresh
dedicated repro instance launched with malloc stack logging.

## Restart Comparison

Ask whether a full cmux restart makes the problem disappear or materially
improves it. If restart helps, capture the fresh process too:

```bash
scripts/sample-cmux.py
scripts/capture-memory.sh --pid <new-pid> --out ~/Desktop/cmux-memory-<new-pid>
```

A useful comparison looks like:

```text
                         slow process     fresh process
process age              12 days          30 seconds
physical footprint       2.2G             858M
main thread waiting      30%              62%
NSView layout            53%              16%
AttributeGraph           26%               5%
```

Exact percentages will vary. The important signal is whether the slow process
has accumulated memory and shifted main-thread time from idle/waiting into
layout, rendering, scanning, or synchronous work.

## What To Look For In A Sample

Start with the header:

```text
Process:
Path:
Version:
Launch Time:
Date/Time:
OS Version:
Physical footprint:
Physical footprint (peak):
```

Then inspect the main thread first. Sleeping worker threads often dominate the
collapsed "top of stack" section but are not necessarily the cause.

Helpful command:

```bash
rg -n "Main Thread|NSView layoutSubtreeIfNeeded|NSHostingView.layout|ViewGraphRootValueUpdater|AttributeGraph|WindowTerminalPortal|GhosttyTerminalView|TabItemView|VerticalTabsSidebar|CmuxTopProcessSnapshot|PaneMemoryGuardrail|PortScanner|WebKit|mach_msg2_trap" ~/Desktop/cmux-samples/<sample>.txt
```

Common interpretations:

- `mach_msg2_trap` high on the main thread means the app was mostly idle during
  the sample.
- `NSView layoutSubtreeIfNeeded`, `NSHostingView.layout`,
  `ViewGraphRootValueUpdater.render`, and `AttributeGraph` indicate AppKit /
  SwiftUI layout work.
- `GeometryReaderLayout`, `ScrollViewLayoutComputer`, `StackLayout`, and
  `LazyLayout` suggest broad SwiftUI layout invalidation, often involving
  sidebar, list, split, or scroll views.
- `WindowTerminalPortal.*` indicates terminal portal install, geometry, or
  hosted-view synchronization work.
- `GhosttyTerminalView.updateNSView`,
  `GhosttySurfaceScrollView.synchronizeGeometryAndContent`, and renderer symbols
  indicate terminal view update or render work.
- `CmuxTopProcessSnapshot`, `PaneMemoryGuardrail`, `PortScanner`,
  `PullRequestProbeService`, or command runner frames can identify background
  polling or diagnostics reaching the main thread.
- `WebKit` frames are only suspicious when they consume meaningful main-thread
  samples or memory; their presence alone is normal if browser panes exist.

Be careful with collapsed top-of-stack output. Large counts for `kevent64`,
`poll`, `__psynch_cvwait`, Sentry, Breakpad, or other waiting threads usually
mean parked background threads, not UI slowness.

## What To Look For In Memory

Open `footprint-summary.txt` and `vmmap-summary.txt`.

Memory categories that often matter:

- `MALLOC_SMALL` / `MALLOC_LARGE`: general Swift/app allocations
- `IOSurface`: terminal/browser/backing surfaces
- `IOAccelerator (graphics)`: GPU-backed graphics memory
- `CoreAnimation`: layer and display state
- `CG image`: image buffers
- `AttributeGraph`: SwiftUI graph data
- `WebKit malloc`: browser process/app-side WebKit allocations

Example concerning shape:

```text
897 MB  MALLOC_SMALL
302 MB  Owned physical footprint (unmapped) (graphics)
265 MB  IOSurface
210 MB  IOAccelerator (graphics)
129 MB  app-specific tag 1
```

That points more toward long-lived app/Swift allocations plus graphics or
terminal surfaces than toward WebKit.

## Useful Questions To Ask

Ask enough to correlate the sample with behavior:

- How long had cmux been running?
- Did restart fix it?
- Is typing slow, scrolling slow, workspace switching slow, or everything slow?
- How many windows, workspaces, terminal panes, and browser panes are open?
- Does closing stale workspaces or browser panes improve it?
- Does it happen only with a specific workspace selected?
- Does Activity Monitor show cmux CPU high while idle, or only during interaction?
- Is the user on stable, nightly, or a tagged debug build?
- Which macOS version is the reporter on?

## Stable Vs Nightly Checks

If stable is slow and `main` has relevant performance changes, test nightly as a
controlled comparison.

Nightly is a separate app with a separate bundle ID:

```text
stable:  com.cmuxterm.app
nightly: com.cmuxterm.app.nightly
```

Session snapshots are stored per bundle ID under:

```text
~/Library/Application Support/cmux/
```

Stable uses:

```text
session-com.cmuxterm.app.json
session-com.cmuxterm.app-previous.json
```

Nightly uses:

```text
session-com.cmuxterm.app.nightly.json
session-com.cmuxterm.app.nightly-previous.json
```

To seed nightly from stable, quit stable first, then copy the snapshots:

```bash
cd "$HOME/Library/Application Support/cmux"
cp session-com.cmuxterm.app.json session-com.cmuxterm.app.nightly.json
cp session-com.cmuxterm.app-previous.json session-com.cmuxterm.app.nightly-previous.json 2>/dev/null || true
```

Then launch `cmux NIGHTLY` and capture the same sample/memory data after using
it normally.

## Debug Build Logs

For a tagged debug build, the unified debug log is:

```bash
tail -f "$(cat /tmp/cmux-last-debug-log-path 2>/dev/null || echo /tmp/cmux-debug.log)"
```

Tagged debug apps write:

```text
/tmp/cmux-debug-<tag>.log
```

Use debug logs to correlate samples with focus, split, tab, mouse, and portal
events. Do not add broad logging to hot paths unless the debug loop needs it,
and keep temporary probes behind `#if DEBUG`.

## Areas To Investigate By Symptom

Typing lag:

- `TerminalSurface.forceRefresh()`
- `GhosttyTerminalView.updateNSView`
- terminal renderer frames
- `WindowTerminalHostView.hitTest()` pointer-event gating
- `TabItemView` `Equatable` behavior and `.equatable()` call sites

Workspace/sidebar lag:

- `ContentView`
- `VerticalTabsSidebar`
- sidebar row snapshots
- `LazyVStack` / `ForEach` invalidation
- notification/unread projections
- workspace title, PR, branch, directory, and port status polling

Split/resize/layout lag:

- `WindowTerminalPortal`
- `GhosttySurfaceScrollView.synchronizeGeometryAndContent`
- `BonsplitController.notifyGeometryChange`
- `Workspace.splitTabBar(_:didChangeGeometry:)`
- repeated portal hide/show or full synchronize calls

Long-lived memory growth:

- terminal surface registry and teardown paths
- hidden or closed terminal surfaces retaining renderers or IOSurfaces
- browser panels and WKWebViews
- CoreAnimation layers
- SwiftUI `AttributeGraph` growth
- retained workspace/session snapshots, notification history, or closed-window
  history

## Reporting Template

Use this structure when handing off an investigation:

```markdown
## Summary

- User-visible behavior:
- Stable/nightly/debug build:
- macOS version:
- Process age:
- Restart helped:

## Captures

- Slow sample:
- Slow memory:
- Fresh sample:
- Fresh memory:

## Main-thread findings

- Main thread total samples:
- Idle/waiting samples:
- Layout/render samples:
- cmux-owned hot frames:

## Memory findings

- Physical footprint:
- Peak footprint:
- Largest footprint/vmmap categories:

## Interpretation

- Most likely area:
- Evidence against alternate explanations:

## Next steps

- Mitigation:
- Follow-up captures:
- Code areas to inspect:
```

