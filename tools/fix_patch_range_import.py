from pathlib import Path
p = Path('tools/patch_range_import.py')
s = p.read_text(encoding='utf-8')
start = s.index('old_report = """')
end = s.index("core.write_text(p, encoding='utf-8')", start)
s = s[:start] + s[end:]
p.write_text(s, encoding='utf-8')
