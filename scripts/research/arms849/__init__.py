"""The three #849 arms and what they share — mission arms-run-01M3APTA.

This package is the code that runs INSIDE the answer-key-free execution boundary
(research.md D-8). Two rules govern everything in it:

1. Anything every arm shares has exactly one definition here — the text form
   (`text`), the registered prompt (`prompt`), the question manifest
   (`questions`) and the serving configuration (`serving`) — so the arms can
   differ only in retrieval. Each returns frozen bytes or a registered
   constant; nothing here computes a value and then treats it as authoritative.

2. Nothing in this package may name, read or reach the hidden answer key, the
   authoring seeds, the narrative files or the provenance table. WP04's gate scans
   every module here for those strings and the run environment physically
   lacks the files; a module that needs answer-key material to work is a defect in
   the design, not a missing feature.

Helpers are invoked as ``python3 -m scripts.research.arms849.<module>``.
"""
