"""A fixture host that is wrong on purpose.

The other three fixtures are exemplary: what they ship is what a host author
copies, so every skill in them is stored the way the Agent Skills spec says to.
That leaves nowhere to keep the *failing* cases, and the negative tests need
real files — a violation reported off a hand-built string proves the message
renders, not that the check finds anything on disk.

So this package holds the counterexamples, and nothing else. Its prompt tree is
deliberately non-conformant, and a skills linter pointed at it is *supposed* to
complain:

    prompts/
    ├── references/stale-commands.md   # a doc naming commands that do not exist
    ├── flat-skill.md                  # a skill body outside any directory
    ├── misfiled/SKILL.md              # frontmatter `name` != its directory
    └── bad-metadata/SKILL.md          # `metadata` values that are not strings

Nothing here is a template. Read `examplehost`, `solohost`, or `multihost` for
that.
"""
