"""Create .env from example.env if it doesn't exist yet.

The scaffolding step the setup flow used to make the candidate do by hand (new file,
name it .env, open example.env, copy, paste). Creating the file is the whole job -- the
values themselves are typed by the candidate directly into the file, so that no
credential has to pass through the conversation.

This script deliberately never reads .env back, never prints its contents, and never
reports which keys are filled. That is check_connections.py's job, and it answers in
status words only. Because this script cannot leak anything, it is safe to allowlist.

Output is only ever one line naming the path.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
EXAMPLE_ENV_PATH = REPO_ROOT / "example.env"


def main() -> int:
    if ENV_PATH.exists():
        # Never overwrite: the file may already hold working credentials, and this
        # script has no way to know -- it can't read it.
        print(f".env already exists at {ENV_PATH}")
        return 0

    if not EXAMPLE_ENV_PATH.exists():
        print(f"ERROR: {EXAMPLE_ENV_PATH} not found -- cannot scaffold .env", file=sys.stderr)
        return 1

    ENV_PATH.write_text(EXAMPLE_ENV_PATH.read_text())
    ENV_PATH.chmod(0o600)  # owner-only, from the moment it exists
    print(f"Created .env at {ENV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
