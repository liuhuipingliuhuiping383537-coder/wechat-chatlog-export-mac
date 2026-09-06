"""生成 ad-hoc 重签名用的授权文件：注入 get-task-allow，保留 app-sandbox。

用法：
  1) 先导出微信原始授权：
       codesign -d --entitlements :- /Applications/WeChat.app > ~/wx_ent_orig.plist
  2) 再跑本脚本生成 ~/wx_ent.plist
"""
import plistlib
import sys
from pathlib import Path

src = Path.home() / "wx_ent_orig.plist"
dst = Path.home() / "wx_ent.plist"

if not src.exists():
    sys.exit(f"[!] 找不到 {src}\n"
             f"    请先执行：codesign -d --entitlements :- /Applications/WeChat.app > {src}")

with open(src, "rb") as f:
    ent = plistlib.load(f)

print("原始权限:")
for k, v in ent.items():
    print("  ", k, "=", v)

# 关键：允许被调试/读取内存
ent["com.apple.security.get-task-allow"] = True

# 注意：app-sandbox 必须保留，否则微信会换数据目录，读不到已有的聊天记录
# 只去掉 ad-hoc 签名下无意义的 team/application 标识
for k in ("com.apple.application-identifier",
          "com.apple.developer.team-identifier"):
    ent.pop(k, None)

with open(dst, "wb") as f:
    plistlib.dump(ent, f)

print("\n写入后的权限:")
for k, v in ent.items():
    print("  ", k, "=", v)
print(f"\n已写入 {dst}")
