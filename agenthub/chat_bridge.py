"""Package/install an owned VS Code participant; Python stdlib only, no model calls."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
from xml.sax.saxutils import escape

from .config import ROOT
from .platforms import resolve_command
from .settings import atomic_json

EXTENSION_ID = 'khang1604.multi-agents-chat'


def code_command(executable):
    """Resolve the official Code shim directly, without executing CMD text."""
    path = Path(executable).resolve()
    environment = dict(os.environ)
    if os.name == 'nt' and path.name.lower() == 'code.cmd':
        script = path.read_text(encoding='utf-8')[:8192]
        match = re.search(r'"%~dp0\.\.\\([^"%]+\\cli\.js)"', script, re.I)
        if not match:
            raise ValueError('Cannot resolve official VS Code CLI entrypoint safely')
        root = path.parent.parent
        cli = (root / match[1]).resolve()
        binary = root / 'Code.exe'
        if not cli.is_relative_to(root) or not cli.is_file() or not binary.is_file():
            raise ValueError('VS Code CLI paths are missing/outside installation')
        environment.update(ELECTRON_RUN_AS_NODE='1', VSCODE_DEV='')
        return [str(binary), str(cli)], environment
    return resolve_command([str(executable)]), environment


def build(home):
    """Package the VS Code extension with pinned runtime paths and verify the VSIX archive."""
    folder = Path(home) / 'integrations/vscode-chat'
    folder.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'integrations/vscode-chat'
    metadata = json.loads((source / 'package.json').read_text(encoding='utf-8'))
    version = metadata['version']
    runtime = {'command': sys.executable, 'args': [str(ROOT / 'cli/ma.py'), '--home',
               str(Path(home).resolve()), 'mcp', '--client', 'vscode-hub-chat']}
    identity = escape(metadata['publisher'])
    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
 <Metadata><Identity Language="en-US" Id="multi-agents-chat" Version="{version}" Publisher="{identity}"/>
 <DisplayName>Multi Agents Hub Chat</DisplayName><Description xml:space="preserve">Direct local Hub participant</Description>
 <Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.93.0"/>
 <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui"/></Properties></Metadata>
 <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/>
 <Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets>
</PackageManifest>'''
    content_types = '''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="json" ContentType="application/json"/>
 <Default Extension="js" ContentType="application/javascript"/>
 <Default Extension="vsixmanifest" ContentType="text/xml"/>
</Types>'''
    target = folder / ('multi-agents-chat-' + version + '.vsix')
    temporary = target.with_suffix('.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('extension.vsixmanifest', manifest)
        for name in ('package.json', 'extension.js', 'transport.js', 'handler.js', 'review.js', 'setup.js'):
            archive.write(source / name, 'extension/' + name)
        archive.writestr('extension/runtime.json', json.dumps(runtime, ensure_ascii=False))
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise ValueError('Chat extension archive failed verification')
    # Versioned local artifact is replaceable; installed extension is never silently replaced.
    temporary.replace(target)
    return target


def install(home, apply=False, runner=None, command=None):
    """Explicitly install or upgrade only an owned VS Code extension and verify its listing."""
    executable = command or shutil.which('code')
    if not executable:
        raise ValueError('VS Code CLI not found; install VS Code or add its bin directory to PATH')
    plan = {'client': 'vscode-chat', 'extension': EXTENSION_ID,
            'status': 'preview; --apply installs @hub into VS Code Copilot Chat',
            'ide_chat_verified': False, 'host_quota_independence_verified': False}
    if not apply:
        return plan
    runner = runner or subprocess.run
    prefix, environment = code_command(executable)
    listed = runner(prefix + ['--list-extensions', '--show-versions'], capture_output=True,
                    encoding='utf-8', errors='replace', timeout=40, env=environment)
    if listed.returncode:
        raise ValueError('Cannot inspect installed VS Code extensions; nothing installed')
    current = next((line.strip() for line in listed.stdout.splitlines()
                    if line.lower().startswith(EXTENSION_ID + '@')), None)
    record_path = Path(home) / 'integrations/vscode-chat.json'
    if current and not record_path.exists():
        raise ValueError('An unowned Hub Chat extension already exists; inspect it before replacing')
    if current:
        owned = json.loads(record_path.read_text(encoding='utf-8'))
        if owned.get('source') != str(ROOT) or owned.get('python') != sys.executable:
            raise ValueError('Installed Hub Chat uses a different source/interpreter; explicit reinstall required')
    package = build(home)
    version = json.loads((ROOT / 'integrations/vscode-chat/package.json').read_text(encoding='utf-8'))['version']
    if current and owned.get('version') != current.split('@')[-1]:
        raise ValueError('Installed Hub Chat version changed outside this installer; existing extension preserved')
    # No --force: the editor retains control over replacement/installation policy.
    result = runner(prefix + ['--install-extension', str(package)], capture_output=True,
                    encoding='utf-8', errors='replace', timeout=90, env=environment)
    if result.returncode:
        raise ValueError('VS Code rejected the extension install; inspect its CLI output locally')
    checked = runner(prefix + ['--list-extensions', '--show-versions'], capture_output=True,
                     encoding='utf-8', errors='replace', timeout=40, env=environment)
    if checked.returncode or (EXTENSION_ID + '@' + version).lower() not in checked.stdout.lower().splitlines():
        raise ValueError('Extension installation could not be confirmed')
    backup = atomic_json(record_path, {'extension': EXTENSION_ID, 'version': version,
                         'package': str(package), 'source': str(ROOT), 'python': sys.executable})
    return {**plan, 'status': 'installed; reload VS Code, then type @hub /agents in Copilot Chat',
            'package': str(package), 'backup': backup}


def check_stdio(home):
    """Check Hub handshake/tools without touching IDE config, source or providers."""
    messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                 'params': {'protocolVersion': '2024-11-05', 'capabilities': {}}},
                {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
    process = subprocess.run([sys.executable, str(ROOT / 'cli/ma.py'), '--home', str(home),
                              'mcp', '--client', 'readiness-check'],
                             input=''.join(json.dumps(message) + '\n' for message in messages),
                             capture_output=True, encoding='utf-8', errors='replace', timeout=20)
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    tools = next((reply.get('result', {}).get('tools') for reply in replies if reply.get('id') == 2), None)
    if process.returncode or not tools or 'dispatch_task' not in {tool['name'] for tool in tools}:
        raise ValueError('Hub MCP handshake/tools check failed; no AI called')
    return {'status': 'OK', 'tools': len(tools), 'ai_calls': 0, 'ide_chat_verified': False}
