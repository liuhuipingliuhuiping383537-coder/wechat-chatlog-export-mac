"""解密微信 WCDB 数据库（普通用户运行）。

页面布局（实测）：
  page 1:  [0:16] salt(明文) | [16:4016] 密文 | [4016:4032] IV | [4032:4096] HMAC-SHA512
  page N:  [0:4016] 密文 | [4016:4032] IV | [4032:4096] HMAC-SHA512
  解密后 page1 的前 16 字节要还原成 "SQLite format 3\\0"
"""
import json
import os
import shutil
import sys
from pathlib import Path

from Crypto.Cipher import AES

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wxconf

PAGE = 4096
CT_END = 4016          # 密文结束偏移
IV_OFF = 4016          # IV 偏移
MAGIC = b"SQLite format 3\x00"

DB_DIR = wxconf.find_db_dir()
OUT_DIR = os.path.join(wxconf.out_base(), "_解密库")
KEYS = wxconf.keys_file()


def decrypt_file(src, dst, key_hex):
    key = bytes.fromhex(key_hex)
    size = os.path.getsize(src)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        page_no = 0
        while True:
            block = fi.read(PAGE)
            if not block:
                break
            if len(block) < PAGE:
                fo.write(block)
                break
            iv = block[IV_OFF:IV_OFF + 16]
            if page_no == 0:
                ct = block[16:CT_END]
                pt = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
                out = MAGIC + pt + b"\x00" * (PAGE - 16 - len(pt))
            else:
                ct = block[0:CT_END]
                pt = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
                out = pt + b"\x00" * (PAGE - len(pt))
            fo.write(out)
            page_no += 1
    return page_no


def main():
    keys = json.load(open(KEYS))
    salt_to_key = {s: v["key"] for s, v in keys.items()}
    only = sys.argv[1:] if len(sys.argv) > 1 else None

    todo = []
    for root, _d, files in os.walk(DB_DIR):
        for name in files:
            if not name.endswith(".db"):
                continue
            if name.endswith("-wal") or name.endswith("-shm"):
                continue
            path = os.path.join(root, name)
            if os.path.getsize(path) < PAGE * 2:
                continue
            rel = os.path.relpath(path, DB_DIR)
            if "/media_" in rel and not only:      # 媒体缓存库，不含聊天记录，跳过以省时间
                continue
            if only and not any(o in rel for o in only):
                continue
            todo.append((rel, path))

    todo.sort(key=lambda x: os.path.getsize(x[1]))
    os.makedirs(OUT_DIR, exist_ok=True)
    done = 0
    for rel, path in todo:
        with open(path, "rb") as f:
            salt = f.read(16).hex()
        key_hex = salt_to_key.get(salt)
        if not key_hex:
            print(f"[SKIP] 无密钥 {rel}")
            continue
        dst = os.path.join(OUT_DIR, rel.replace("/", "_"))
        pages = decrypt_file(path, dst, key_hex)
        mb = os.path.getsize(path) / 1024 / 1024
        print(f"[OK] {rel} ({mb:.0f}MB, {pages} 页)")
        done += 1
    print(f"\n完成 {done} 个，输出目录 {OUT_DIR}")


if __name__ == "__main__":
    main()
