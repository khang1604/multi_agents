"""Local terminal menu; monitoring does not call an AI model."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agenthub.api import Hub
from agenthub.config import default_home
from agenthub.service import start_daemon, stop_daemon, daemon_status
from cli.hub import doctor, make_demo


def show(value):
    """Print a terminal-menu result as formatted JSON."""
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    """Run the legacy menu and route actions to the shared Hub without AI status polling."""
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11 or later is required.')
    hub = Hub(default_home())
    while True:
        print('\nAGENT HUB PRIVATE — Auto / conserve quota')
        print('1 Check CLIs   2 Create demo   3 Submit task   4 Progress')
        print('5 Start orchestrator   6 Stop   7 MCP configuration   8 Demo without quota usage   0 Exit menu')
        choice = input('Choose: ').strip()
        try:
            if choice == '0':
                print('Closing the menu does not stop the daemon. Choose 6 to stop it.')
                return
            if choice == '1': show(doctor(hub))
            elif choice == '2': show(make_demo(hub))
            elif choice == '3':
                projects = hub.store.all('SELECT name,path FROM projects')
                show(projects)
                project = input('Project name: ').strip()
                objective = input('Objective: ').strip()
                key = input('Unique request key (e.g. todo-filter-1): ').strip()
                show(hub.start(project, objective, key))
            elif choice == '4':
                show({'daemon': daemon_status(hub.store.home), 'workflows': hub.store.all(
                    'SELECT id,status,phase,leader,complexity,calls,max_calls,workspace,error FROM workflows ORDER BY updated DESC LIMIT 20')})
            elif choice == '5': show(start_daemon(hub.store.home))
            elif choice == '6': show(stop_daemon(hub.store.home))
            elif choice == '7':
                subprocess.run([sys.executable, str(ROOT/'cli/hub.py'), '--home', str(hub.store.home), 'mcp-config'], check=True)
            elif choice == '8':
                from agenthub.simulation import simulate
                show(simulate())
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            print('Error:', error)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: main()
    except (KeyboardInterrupt, EOFError): print('\nMenu closed; daemon state is unchanged.')
