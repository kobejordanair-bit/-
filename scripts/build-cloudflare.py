"""Package only the legal typing frontend for Cloudflare Pages."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'dist' / 'lawtype'
FILES = (
    'index.html', 'exam-practice.css', 'exam-practice.mjs', 'exam-tools.mjs', 'exam-storage.mjs',
    'typing-metrics.mjs', 'essay-tools.mjs', 'legal-import.mjs',
    'cloud-sync.mjs', 'supabase-sync.mjs', 'supabase-config.mjs',
)


def main():
    if OUTPUT.resolve() != (ROOT.resolve() / 'dist' / 'lawtype'):
        raise ValueError('Build output must stay inside this repository')
    for name in FILES:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(ROOT / name, OUTPUT / name)
    # Explicit asset types for ES modules; prevent stale HTML after deployments.
    (OUTPUT / '_headers').write_text(
        '/\n  Cache-Control: no-cache\n'
        '/index.html\n  Cache-Control: no-cache\n'
        '/*.mjs\n  Content-Type: text/javascript; charset=utf-8\n'
        '  Cache-Control: no-cache\n'
        '/exam-practice.css\n  Cache-Control: no-cache\n', encoding='utf-8'
    )
    (OUTPUT / '404.html').write_text(
        '<!doctype html><html lang="zh-TW"><meta charset="utf-8">'
        '<title>找不到頁面</title><h1>找不到頁面</h1><a href="/">返回打字系統</a></html>',
        encoding='utf-8'
    )
    print(f'Cloudflare Pages output: {OUTPUT} ({len(FILES)} frontend files)')


if __name__ == '__main__':
    main()
