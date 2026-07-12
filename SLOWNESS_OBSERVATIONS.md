# cmux Slowness Observations

This file records evidence from specific slow cmux hosts. Keep the reusable
capture procedure and symbol interpretation in `SLOWNESS_DEBUGGING.md`; keep
measurements, hypotheses, and outcomes here.

Do not assume two hosts have the same cause merely because both feel slow.
Record raw captures before applying a mitigation, then compare like-for-like
captures after restart, upgrade, or reducing the number of open surfaces.

## Cross-host findings

- A full restart is a useful controlled experiment, not just a workaround. On
  Host A it reduced physical footprint and substantially increased main-thread
  idle time.
- Inspect the main thread rather than treating parked worker-thread stacks as
  evidence of a bottleneck.
- The presence of WebKit frames or browser panes is not enough to blame WebKit.
  On Host A, WebKit memory was small while general allocations and graphics
  memory were large.
- Process age, app version, macOS version, and open surface counts are necessary
  context. Without them, samples from different hosts are hard to compare.
- A sample taken immediately after restart can contain session restoration and
  terminal portal startup work. Record how many seconds the app had been
  running when each capture was taken.
- Current evidence supports a layout-churn/retained-state hypothesis for Host A,
  but does not yet identify the retaining object or prove that Host B has the
  same failure mode.

## Host A: long-lived stable process (2026-07-06)

### User-visible behavior

- cmux became slow after a long period without a restart.
- Restarting cmux materially improved responsiveness.

### Environment

```text
App:                 stable /Applications/cmux.app
Version:             0.64.17 (97)
Process age (slow):  11d 23h 56m
macOS version:       not recorded
Hardware:            not recorded
Open surface counts: not recorded
```

The missing host and topology fields limit comparison with later reports.

### Captures

The original captures were stored outside the repository:

```text
Slow sample:         ~/Desktop/cmux-samples/cmux-69023-20260706-150223.sample.txt
Slow memory:         ~/Desktop/cmux-memory-69023/
Fresh sample:        ~/Desktop/cmux-samples/cmux-52956-20260706-151542.sample.txt
Fresh memory:        not captured or not recorded
```

### Before/after comparison

```text
                              slow             fresh after restart
PID                           69023            52956
Process age                   11d 23h 56m      31s
Physical footprint            1.9-2.2G         858.9M
Peak physical footprint       2.3G             1.0G
Main-thread samples           11166            13590
Waiting in mach_msg           3332  (~30%)     8414  (~62%)
NSView layout                 5961  (~53%)     2239  (~16%)
NSHostingView.layout          3019  (~27%)     1955  (~14%)
AttributeGraph                2899  (~26%)      745  (~5%)
Geometry/Scroll/Stack layout  2489  (~22%)      ~9-31 (negligible)
```

The slow process's dominant main-thread shape was:

```text
NSApplication run
  CoreFoundation run loop observers
    AppKit/QuartzCore transaction flush
      NSWindow layoutIfNeeded
        NSView layoutSubtreeIfNeeded
          NSHostingView.layout
            ViewGraphRootValueUpdater.render
              AttributeGraph update
                GeometryReaderLayout
                ScrollViewLayoutComputer
                StackLayout
```

The fresh sample contained about 303 samples in
`WindowTerminalPortal.scheduleDeferredFullSynchronizeAll`, `ensureInstalled`,
and `synchronizeLayoutHierarchy`. Because it was captured 31 seconds after
launch, this may be restoration noise rather than steady-state churn.

### Slow-process memory

```text
897 MB  MALLOC_SMALL
302 MB  owned physical footprint (unmapped), graphics
265 MB  IOSurface
210 MB  IOAccelerator graphics
129 MB  app-specific tag 1
 59 MB  MALLOC_LARGE
 45 MB  untagged VM_ALLOCATE
 18 MB  CG image
```

Additional `vmmap` observations:

```text
DefaultMallocZone allocated:           638.5M
DefaultMallocZone dirty + swapped:     915.3M
AttributeGraph allocated:               20.2M
AttributeGraph graph data allocated:     7.7M
IOSurface resident:                    264.8M
IOAccelerator graphics resident:       209.7M
WebKit malloc (footprint):               1.9M
WebKit Malloc allocated (vmmap):         265K
```

### Interpretation

Restarting reduced footprint by roughly 1.1-1.3G and shifted the main thread
from sustained layout work toward waiting. The evidence is consistent with
long-lived app/view state making SwiftUI/AppKit layout more expensive and with
general allocations plus terminal/graphics surfaces accumulating.

This evidence does not prove a leak, identify a retaining object, or establish
that portal synchronization is the root cause. It does provide evidence against
WebKit being the primary memory contributor on this host.

Areas worth testing were:

- hidden or closed terminal surfaces retaining renderers or IOSurfaces
- stale workspaces, tabs, or surfaces retaining SwiftUI graph state
- broad sidebar/workspace/tab invalidation repeatedly triggering layout
- portal geometry synchronization over-invalidating AppKit/SwiftUI layout

## Host B: current slow host

Status: awaiting the first capture. Fill this section before restarting cmux.

### Environment and symptom

```text
Date/time:
Hostname or host label:
Hardware / memory:
macOS version:
App channel (stable/nightly/debug):
App version/build:
Process PID:
Process launch time/age:

What feels slow (typing/scrolling/switching/everything):
CPU while idle:
CPU during the slow interaction:
Selected workspace-specific:
Restart already attempted:

Windows:
Workspaces:
Terminal panes:
Browser panes:
Other pane types:
```

### Capture while slow

Run from this checkout while the bad behavior is occurring:

```bash
scripts/sample-cmux.py --list
scripts/sample-cmux.py --pid <pid> --duration 30
scripts/capture-memory.sh --pid <pid> --out ~/Desktop/cmux-memory-host-b-slow-<pid>
```

Record the output paths and observations:

```text
Slow sample:
Slow memory directory:
Physical footprint / peak:
Main-thread total samples:
Main-thread waiting samples:
NSView / NSHostingView layout samples:
AttributeGraph samples:
cmux-owned hot frames:
Largest memory categories:
```

### Controlled comparisons

Perform one change at a time and record what changed perceptibly and in the
captures.

1. Close stale panes/workspaces, if safe, and repeat sample plus memory capture.
2. Fully restart the same app version, restore the same topology, wait for
   restoration to settle, and repeat sample plus memory capture.
3. If the stable build was slow, test nightly with the same topology and normal
   workload. Do not treat a fresh nightly process versus an old stable process
   as a version-only comparison; process age is a confounder.

```text
Comparison performed:
Time since comparison process launched:
Topology differences:
User-visible result:
Comparison sample:
Comparison memory directory:
Physical footprint / peak:
Main-thread waiting:
Layout / AttributeGraph:
Largest memory categories:
```

### Host B conclusions

```text
Facts established:
Leading hypothesis:
Evidence supporting it:
Evidence against alternatives:
Unknowns:
Next discriminating experiment:
Immediate mitigation:
```

## Investigation log

Add short dated entries as Host B is investigated. Link raw captures; do not
paste entire `sample`, `footprint`, or `vmmap` outputs into this file.

```text
YYYY-MM-DD HH:MM TZ — observation or experiment
- State/change:
- Result:
- Capture paths:
- Interpretation:
- Next check:
```
