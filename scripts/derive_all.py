"""用抓到的 passphrase 派生全部微信数据库密钥（普通用户运行）。"""
import hashlib
import hmac as hmac_mod
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wxconf

SALTS = str(wxconf.TMP / "salts.json")
HITS = str(wxconf.TMP / "pbkdf_hits.jsonl")
OUT = wxconf.keys_file()
PAGE_SZ = 4096
KEY_SZ = 32


def verify(enc_key, page1):
    salt = page1[:16]
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SZ)
    hm = hmac_mod.new(mac_key, page1[16: PAGE_SZ - 80 + 16], hashlib.sha512)
    hm.update(struct.pack("<I", 1))
    return hm.digest() == page1[PAGE_SZ - 64: PAGE_SZ]


salts = json.load(open(SALTS))

# 收集候选 passphrase：rounds 很大（256000）的那次调用
cands = []
for line in open(HITS):
    p = json.loads(line)
    if p.get("type") == "cckey" and p.get("rounds", 0) >= 1000 and p.get("pwLen") == 32:
        cands.append(p["pw"])
cands = list(dict.fromkeys(cands))
print(f"候选 passphrase {len(cands)} 个")
for c in cands:
    print("  ", c)

keys = {}
for pw_hex in cands:
    pw = bytes.fromhex(pw_hex)
    for salt_hex, v in salts.items():
        if salt_hex in keys:
            continue
        enc = hashlib.pbkdf2_hmac("sha512", pw, bytes.fromhex(salt_hex), 256000, dklen=KEY_SZ)
        if verify(enc, bytes.fromhex(v["page1"])):
            keys[salt_hex] = {"key": enc.hex(), "mode": "pbkdf2",
                              "passphrase": pw_hex, "dbs": v["dbs"]}

print(f"\n解出 {len(keys)}/{len(salts)} 个数据库密钥")
for s, v in keys.items():
    print("  OK", v["dbs"][0])

if keys:
    json.dump(keys, open(OUT, "w"), indent=2)
    print("\n已写入", OUT)
