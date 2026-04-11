---
title: "Broken frontmatter
status: [unclosed
tags: {not: "a, valid, mapping
---

Body text. The YAML above is intentionally broken — unterminated strings
and unclosed brackets. `yaml.safe_load` should raise `yaml.YAMLError` and
the helper should treat this file as unprocessed.
