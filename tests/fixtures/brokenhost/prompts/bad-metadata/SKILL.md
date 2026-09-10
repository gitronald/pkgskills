---
name: bad-metadata
description: A skill whose metadata is not the string-to-string map the spec requires.
metadata:
  author: example-org
  version: 1.0
  retries: 3
  enabled: true
  owner:
    team: platform
---

# bad-metadata

`author` is fine — an unquoted plain scalar is still a string. The rest are
not: `1.0` is a float, `3` an integer, `true` a boolean, and `owner` opens a
nested mapping where a string value belongs.
