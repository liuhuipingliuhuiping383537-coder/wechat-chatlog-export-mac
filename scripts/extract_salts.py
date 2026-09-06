"""读取所有微信数据库的第一页（含 salt），存为 /tmp/wxdb/salts.json。
以普通用户运行（root 反而会被 TCC 拒绝访问微信容器目录）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wxconf

DB_DIR = wxconf.find_db_dir()
OUT = str(wxconf.TMP / "salts.json")
PAGE_SZ = 4096

os.makedirs(wxconf.TMP, exist_ok=True)
data = {}
count = 0
for root, _d, files in os.walk(DB_DIR):
    for name in files:
        if not name.endswith(".db"):
            continue
        if name.endswith("-wal") or name.endswith("-shm"):
            continue
        path = os.path.join(root, name)
        try:
            if os.path.getsize(path) < PAGE_SZ * 2:
                continue
            with open(path, "rb") as f:
                page1 = f.read(PAGE_SZ)
        except OSError as e:
            print("跳过", name, e)
            continue
        salt = page1[:16].hex()
        rel = os.path.relpath(path, DB_DIR)
        item = data.setdefault(salt, {"dbs": [], "page1": page1.hex()})
        item["dbs"].append(rel)
        count += 1

with open(OUT, "w") as f:
    json.dump(data, f)

print(f"数据库文件 {count} 个，不同 salt {len(data)} 个 -> {OUT}")
for s, v in list(data.items())[:5]:
    print(" ", s[:24], v["dbs"][:2])
