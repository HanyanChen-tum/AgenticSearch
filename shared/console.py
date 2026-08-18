"""Keep console writes from killing a question.

The agent loop prints every model response and every REPL result, and REPL
results carry database rows. On a Windows box whose ANSI codepage is not UTF-8
(this project's is cp936) `sys.stdout.encoding` is that codepage, so a row
holding a character outside it raises UnicodeEncodeError from inside
`complete_sql`. The runner catches it, records `termination` as the exception
name, and stores an empty SQL -- the question is scored wrong for a reason that
has nothing to do with the model.

It is not random: it selects questions whose database content is non-Latin, and
it landed on 0.5%-3.2% of questions depending on the run, a spread the size of
the effects being measured. Reconfiguring here fixes it at the stream instead of
the print sites, so no future print can reintroduce it.
"""

from __future__ import annotations

import sys


def force_utf8_console() -> None:
    """Make stdout/stderr encode UTF-8 and never raise on unencodable text."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # already replaced by a non-text wrapper
            continue
        reconfigure(encoding="utf-8", errors="replace")
