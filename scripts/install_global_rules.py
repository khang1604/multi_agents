"""Preview by default; append bounded rules, preserving existing instructions and backups."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil

START = '<!-- AGENT-HUB-GLOBAL-RULES:START -->'
END = '<!-- AGENT-HUB-GLOBAL-RULES:END -->'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    rules = (root / 'GLOBAL_RULES.md').read_text(encoding='utf-8')
    home = Path.home()
    targets = [Path(os.environ.get('CODEX_HOME', home / '.codex')) / 'AGENTS.md',
               home / '.claude' / 'CLAUDE.md', home / '.copilot' / 'copilot-instructions.md',
               home / '.gemini' / 'GEMINI.md']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for target in targets:
        print(('APPLY ' if args.apply else 'PREVIEW ') + str(target))
        if not args.apply:
            continue
        if target.is_symlink():
            raise ValueError('Refusing symlink: ' + str(target))
        text = target.read_text(encoding='utf-8') if target.exists() else ''
        if START in text or END in text:
            if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
                raise ValueError('Malformed rules markers: ' + str(target))
            text = text[:text.index(START)] + text[text.index(END) + len(END):]
        updated = text.rstrip() + '\n\n' + START + '\n' + rules + '\n' + END + '\n'
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = target.with_name(target.name + '.backup-' + stamp)
            shutil.copy2(target, backup)
            print('BACKUP ' + str(backup))
        target.write_text(updated, encoding='utf-8')
    print('Restart agent sessions to reload instructions. Rules do not grant or enforce OS permissions.')


if __name__ == '__main__':
    main()
