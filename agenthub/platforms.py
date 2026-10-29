"""Small platform boundary: locking, direct execution, and process-tree cleanup."""
import os
from pathlib import Path
import shutil
import signal
import platform
import subprocess
import sys


class AlreadyRunning(Exception):
    pass


class FileLock:
    def __init__(self, path):
        """Initialize FileLock state and its configured dependencies."""
        self.path = Path(path)
        self.file = None

    def __enter__(self):
        """Acquire the platform-specific file lock before accessing shared state."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b'0'); self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            self.file = None
            raise AlreadyRunning('Another daemon owns this data directory') from error
        return self

    def __exit__(self, *_):
        """Release the owned file lock and close its handle."""
        if self.file:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()


def resolve_command(prefix):
    """Resolve Windows npm shims to node scripts; never pass prompts through cmd.exe."""
    if not isinstance(prefix, list) or not prefix or not all(isinstance(x, str) for x in prefix):
        raise ValueError('Provider command must be an argument array')
    found = shutil.which(prefix[0]) or (prefix[0] if Path(prefix[0]).is_file() else None)
    if not found:
        raise FileNotFoundError(prefix[0] + ' is not installed/on PATH')
    # POSIX multicall launchers (including Snap) depend on the invoked alias.
    path = Path(found).resolve() if os.name == "nt" else Path(os.path.abspath(found))
    if os.name == 'nt' and path.suffix.lower() in {'.cmd', '.bat', '.ps1'}:
        # npm optional native packages may be hoisted or nested. Prefer their native .exe.
        name = path.stem.lower()
        arch = 'arm64' if platform.machine().lower() in {'arm64','aarch64'} else 'x64'
        scope = '@openai' if name == 'codex' else '@github' if name == 'copilot' else None
        if scope:
            modules = path.parent / 'node_modules'
            package = f'{name}-win32-{arch}'
            native_roots = [modules/scope/package, modules/scope/name/'node_modules'/scope/package, modules/scope/name/'vendor']
            for native_root in native_roots:
                if native_root.is_dir():
                    found_native = sorted(native_root.rglob(name + '.exe'))
                    if found_native:
                        return [str(found_native[0])] + prefix[1:]
        candidates = {
            'npm': ['npm/bin/npm-cli.js'],
            'npx': ['npm/bin/npx-cli.js'],
            'codex': ['@openai/codex/bin/codex.js'],
            'copilot': ['@github/copilot/index.js', '@github/copilot/dist/index.js'],
            'claude': ['@anthropic-ai/claude-code/cli.js'],
        }.get(path.stem.lower(), [])
        for candidate in candidates:
            script = path.parent / 'node_modules' / candidate
            if script.is_file():
                adjacent_node = path.parent / 'node.exe'
                node = str(adjacent_node) if name in {'npm', 'npx'} and adjacent_node.is_file() else shutil.which('node')
                if node:
                    return [node, str(script)] + prefix[1:]
        raise ValueError('Cannot safely resolve Windows shim ' + str(path) +
                         '. Configure the native .exe or [node.exe, entry.js] in config.json.')
    return [str(path)] + prefix[1:]


def spawn(command, **kwargs):
    """Start a direct child process with platform-specific isolation of its process group."""
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs['start_new_session'] = True
    return subprocess.Popen(command, shell=False, **kwargs)


def stop_tree(process):
    """Stop an owned child process tree and confirm whether it exited."""
    if process.poll() is not None:
        return True
    try:
        if os.name == 'nt':
            taskkill = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/taskkill.exe'
            subprocess.run([str(taskkill), '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=15)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return process.poll() is not None
    return True


def pid_alive(pid):
    """Check process liveness conservatively across Windows and POSIX."""
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied is not evidence of death.
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        # A zombie cannot write files and is safe to recover past.
        stat = Path(f'/proc/{pid}/stat')
        if stat.exists() and stat.read_text().rsplit(')', 1)[1].strip().startswith('Z'):
            return False
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
