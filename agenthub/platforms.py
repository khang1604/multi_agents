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
        home = Path.home()
        local_app = Path(os.environ['LOCALAPPDATA']) if 'LOCALAPPDATA' in os.environ else None
        roaming_app = Path(os.environ['APPDATA']) if 'APPDATA' in os.environ else None
        extra_agy = [p for p in [local_app / 'Programs/Antigravity/bin/agy' if local_app else None,
                                 roaming_app / 'npm/agy' if roaming_app else None] if p]
        extra_codex = [p for p in [roaming_app / 'npm/codex' if roaming_app else None,
                                   local_app / 'Programs/Codex/codex' if local_app else None] if p]
        extra_claude = [p for p in [roaming_app / 'npm/claude' if roaming_app else None] if p]
        extra_copilot = [p for p in [roaming_app / 'npm/copilot' if roaming_app else None] if p]

        fallbacks = {
            'agy': [
                home / '.gemini/bin/agy',
                home / '.local/share/MultiAgents/runtime/bin/agy',
                home / '.local/bin/agy',
            ] + extra_agy,
            'codex': [
                home / '.codex/plugins/.plugin-appserver/codex',
                home / '.config/Code/agent-host/sdk-cache/codex/0.163.0/linux-x64/node_modules/.bin/codex',
                home / '.local/share/MultiAgents/runtime/bin/codex',
                home / '.local/bin/codex',
            ] + extra_codex,
            'claude': [
                home / '.local/bin/claude',
                home / '.config/Code/agent-host/sdk-cache/claude',
                home / '.npm-global/bin/claude',
            ] + extra_claude,
            'copilot': [
                home / '.local/bin/copilot',
                home / '.npm-global/bin/copilot',
            ] + extra_copilot,
        }.get(prefix[0].lower(), [])
        for candidate in fallbacks:
            checks = [candidate]
            if os.name == 'nt':
                checks.extend([candidate.with_suffix('.cmd'), candidate.with_suffix('.exe'), candidate.with_suffix('.bat')])
            for target in checks:
                if target.is_file():
                    found = str(target)
                    break
            if found:
                break
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


def assign_job_object(process):
    """Assign an owned Windows child process to a Job Object that auto-terminates child trees on exit."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            return None
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [('ReadOperationCount', ctypes.c_uint64),
                        ('WriteOperationCount', ctypes.c_uint64),
                        ('OtherOperationCount', ctypes.c_uint64),
                        ('ReadTransferCount', ctypes.c_uint64),
                        ('WriteTransferCount', ctypes.c_uint64),
                        ('OtherTransferCount', ctypes.c_uint64)]
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                        ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD),
                        ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t),
                        ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t),
                        ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ('IoInfo', IO_COUNTERS),
                        ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryLimit', ctypes.c_size_t),
                        ('PeakJobMemoryLimit', ctypes.c_size_t)]
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if hasattr(process, '_handle') and process._handle:
            kernel.AssignProcessToJobObject(job, int(process._handle))
        return job
    except Exception:
        return None


def apply_landlock(workspace_path):
    """Restrict Linux child process filesystem access using Landlock LSM (Kernel 5.13+)."""
    if os.name != 'posix' or not sys.platform.startswith('linux'):
        return False
    try:
        import ctypes
        SYS_landlock_create_ruleset = 444
        SYS_landlock_add_rule = 445
        SYS_landlock_restrict_self = 446
        PR_SET_NO_NEW_PRIVS = 38
        libc = ctypes.CDLL(None, use_errno=True)

        class LandlockRulesetAttr(ctypes.Structure):
            _fields_ = [('handled_access_fs', ctypes.c_uint64)]

        class LandlockPathBeneathAttr(ctypes.Structure):
            _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int32)]

        abi = libc.syscall(SYS_landlock_create_ruleset, None, 0, 1)
        if abi < 1:
            return False

        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            return False

        ACCESS_FS_RO = (1 | 4 | 8)
        ACCESS_FS_ALL = 0x1fff

        attr = LandlockRulesetAttr(ACCESS_FS_ALL)
        ruleset_fd = libc.syscall(SYS_landlock_create_ruleset, ctypes.byref(attr), ctypes.sizeof(attr), 0)
        if ruleset_fd < 0:
            return False

        ro_candidates = ['/usr', '/lib', '/lib64', '/bin', '/etc', '/dev', '/tmp', os.path.expanduser('~')]
        for p in ro_candidates:
            if os.path.exists(p):
                try:
                    fd = os.open(p, os.O_PATH | os.O_CLOEXEC)
                    path_attr = LandlockPathBeneathAttr(ACCESS_FS_RO, fd)
                    libc.syscall(SYS_landlock_add_rule, ruleset_fd, 1, ctypes.byref(path_attr), 0)
                    os.close(fd)
                except OSError:
                    pass

        ws_str = str(workspace_path)
        if os.path.exists(ws_str):
            try:
                fd = os.open(ws_str, os.O_PATH | os.O_CLOEXEC)
                path_attr = LandlockPathBeneathAttr(ACCESS_FS_ALL, fd)
                libc.syscall(SYS_landlock_add_rule, ruleset_fd, 1, ctypes.byref(path_attr), 0)
                os.close(fd)
            except OSError:
                pass

        res = libc.syscall(SYS_landlock_restrict_self, ruleset_fd, 0)
        os.close(ruleset_fd)
        return res == 0
    except Exception:
        return False


def spawn(command, workspace=None, **kwargs):
    """Start a direct child process with platform-specific isolation of its process group."""
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs['start_new_session'] = True
    process = subprocess.Popen(command, shell=False, **kwargs)
    if os.name == 'nt':
        process._job_object = assign_job_object(process)
    return process


def stop_tree(process):
    """Stop an owned child process tree and confirm whether it exited."""
    if process.poll() is not None:
        return True
    try:
        if os.name == 'nt':
            job = getattr(process, '_job_object', None)
            if job:
                try:
                    import ctypes
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.TerminateJobObject(job, 1)
                    kernel.CloseHandle(job)
                    process._job_object = None
                except Exception:
                    pass
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
