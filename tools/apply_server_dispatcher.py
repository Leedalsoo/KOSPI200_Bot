from pathlib import Path

TARGET = Path("web_interface/server.py")
BACKUP = TARGET.with_suffix(TARGET.suffix + ".bak_stage2")

NEW_CONTENT = r'''PASTE_THE_COMPLETE_web_interface_server.py_CODE_FROM_THE_PRECEDING_NOTION_PAGE_HERE'''

if not TARGET.exists():
    raise FileNotFoundError(TARGET)

BACKUP.write_text(TARGET.read_text(encoding="utf-8"), encoding="utf-8")
TARGET.write_text(NEW_CONTENT, encoding="utf-8")
print(f"Applied: {TARGET}")
print(f"Backup : {BACKUP}")