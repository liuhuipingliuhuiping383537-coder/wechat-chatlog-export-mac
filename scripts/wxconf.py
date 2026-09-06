"""公共配置：自动定位微信数据目录与输出目录。

所有路径都不硬编码任何个人信息：
  - 微信数据目录：自动在 ~/Library/Containers/... 下查找
  - 输出目录：默认 ~/wechat-export，可用环境变量 WX_OUT_DIR 覆盖
"""
import os
import sys
from pathlib import Path

CONTAINER = Path.home() / (
    "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
)
TMP = Path("/tmp/wxdb")


def find_db_dir():
    """定位 db_storage 目录（每个微信号一个子目录）。

    多账号时可用环境变量 WX_DB_DIR 指定，或用 WX_UID 指定子目录名。
    """
    env = os.environ.get("WX_DB_DIR")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return str(p)
        sys.exit(f"[!] WX_DB_DIR 不存在: {p}")

    if not CONTAINER.is_dir():
        sys.exit(f"[!] 找不到微信数据目录: {CONTAINER}\n"
                 f"    请设置环境变量 WX_DB_DIR 指向 db_storage 目录")

    uid = os.environ.get("WX_UID")
    if uid:
        p = CONTAINER / uid / "db_storage"
        if p.is_dir():
            return str(p)
        sys.exit(f"[!] 找不到 {p}")

    cands = sorted(p for p in CONTAINER.glob("*/db_storage") if p.is_dir())
    if not cands:
        sys.exit(f"[!] 在 {CONTAINER} 下没有找到任何 db_storage 目录")
    if len(cands) > 1:
        # 取消息数最多（体积最大）的那个，通常是主账号
        def size(p):
            return sum(f.stat().st_size for f in p.glob("*.db") if f.is_file())
        cands.sort(key=size, reverse=True)
        print(f"[i] 发现 {len(cands)} 个账号目录，使用最大的：{cands[0].parent.name}")
    return str(cands[0])


def out_base():
    """导出结果根目录，默认 ~/wechat-export。"""
    return str(Path(os.environ.get("WX_OUT_DIR", "~/wechat-export")).expanduser())


def keys_file():
    return str(Path(os.environ.get("WX_KEYS", TMP / "all_keys.json")))
