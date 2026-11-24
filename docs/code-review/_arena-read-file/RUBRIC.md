# project.read_file design rubric

Grade each DESIGN.md 0-2 per criterion.

1. Bound-workspace safety: escape/`..`/missing root fail honestly.
2. Dual of write: same resolve path as list_files/write_file; model can read then edit.
3. Honesty: binary/missing/too-large are errors or explicit truncated flags, never fake empty ok.
4. Diff size: fewest new concepts; reuse resolve_under_root / resolve_bound_work_root.
5. Testability: names concrete failing self-check cases before success path.
6. No forbidden paths: no Theia agent loop, no computer_use, no Hermes terminal.
