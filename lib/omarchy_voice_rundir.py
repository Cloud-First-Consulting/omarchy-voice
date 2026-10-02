"""The private runtime directory, for the Python scripts.

    from omarchy_voice_rundir import run_dir
    path = run_dir()          # a pathlib.Path, or OSError

Recordings, the transcript history and the listener's state live there, so it
has to be ours and nobody else's. $XDG_RUNTIME_DIR is that by construction.
Without it the fallback is /tmp/omarchy-voice-<uid>, and a name is not
ownership: another local user can create that path first. So each level is
created with mode 0700 if absent and then *checked* - a real directory, not a
symlink, owned by this user, mode 0700 after a chmod that must succeed - and
anything else raises, so the caller stops before it records or writes.
"""

import os
import pathlib
import stat

NAME = "omarchy-voice"


def private_dir(path):
    """Create `path` mode 0700 if absent, then insist it is a real directory
    owned by this user and mode 0700, or raise OSError."""
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise OSError(f"{path} is a symlink, not a private directory of ours")
    if not stat.S_ISDIR(st.st_mode):
        raise OSError(f"{path} is not a directory")
    if st.st_uid != os.getuid():
        raise OSError(f"{path} is owned by uid {st.st_uid}, not us; refusing to use it")
    os.chmod(path, 0o700)
    if stat.S_IMODE(os.lstat(path).st_mode) != 0o700:
        raise OSError(f"{path} could not be made private")
    return path


def run_dir():
    """The private runtime directory, established, or OSError."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        base = pathlib.Path(runtime)
    else:
        base = private_dir(pathlib.Path(f"/tmp/{NAME}-{os.getuid()}"))
    return private_dir(base / NAME)
