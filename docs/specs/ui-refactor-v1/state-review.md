# UI state coverage — Round 14a

Status: TEST SOURCE READY; CI acceptance pending.


While the corrected exact-source run is executing, add eight actual-page scenarios at960x640: empty workspace/FRP/software, long workspace identity/path, partial secret read failure, empty/failed task list, dark native-HTML-dialog focus containment, and live system-theme changes. These reuse the real production routes/components and synthetic IPC, with labelled state screenshots. No business source changes in this round. The shared task panel still needs visual review along with the state images; no native acceptance or all-state completeness is inferred.

Local strict Svelte/type check remains0 errors/0 warnings and all160 frontend tests pass after these additions. The actual-page scenarios must still execute on the candidate in Actions; Python compilation is not runtime browser proof.
