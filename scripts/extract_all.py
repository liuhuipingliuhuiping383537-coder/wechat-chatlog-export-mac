"""从解密后的微信数据库提取全部聊天记录，按会话导出为 Markdown。"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wxconf

BASE = wxconf.out_base()
DECRYPTED = os.path.join(BASE, "_解密库")
OUT = os.path.join(BASE, "chats")
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

dctx = zstandard.ZstdDecompressor()


def decompress(b):
    if not b:
        return b""
    if b[:4] == ZSTD_MAGIC:
        try:
            return dctx.decompress(b, max_output_size=64 * 1024 * 1024)
        except Exception:
            return b""
    return b


def to_text(b):
    if b is None:
        return ""
    if isinstance(b, str):
        return b
    b = decompress(b)
    try:
        return b.decode("utf-8", "replace")
    except Exception:
        return ""


def load_contacts():
    """username -> 显示名"""
    path = os.path.join(DECRYPTED, "contact_contact.db")
    names = {}
    if not os.path.exists(path):
        return names
    con = sqlite3.connect(path)
    cols = [r[1].decode() if isinstance(r[1], bytes) else r[1]
            for r in con.execute("PRAGMA table_info(contact)")]
    con.text_factory = bytes
    idx = {c: i for i, c in enumerate(cols)}
    for row in con.execute("select * from contact"):
        def g(k):
            i = idx.get(k)
            if i is None or row[i] is None:
                return b""
            return row[i] if isinstance(row[i], bytes) else str(row[i]).encode()
        user = to_text(g("username"))
        if not user:
            continue
        remark = to_text(g("remark"))
        nick = to_text(g("nick_name") if "nick_name" in idx else b"")
        alias = to_text(g("alias"))
        display = remark or nick or alias or user
        names[user] = display
    # 补充：name2id 里的 username（通讯录没有名字的，至少显示 wxid）
    try:
        for (u,) in con.execute("select username from name2id"):
            if isinstance(u, bytes):
                u = u.decode("utf-8", "replace")
            if u and u not in names:
                names[u] = u
    except Exception as e:
        print("  name2id 读取失败:", e)
    con.close()
    return names


def load_session_summary():
    """username -> 最后一条消息摘要"""
    path = os.path.join(DECRYPTED, "session_session.db")
    out = {}
    if not os.path.exists(path):
        return out
    con = sqlite3.connect(path)
    con.text_factory = bytes
    try:
        for u, s in con.execute("select username, summary from SessionTable"):
            if isinstance(u, bytes):
                u = u.decode("utf-8", "replace")
            txt = to_text(s).replace("\n", " ")
            out[u] = txt[:80]
    except Exception as e:
        print("  会话摘要读取失败:", e)
    con.close()
    return out


TYPE_MAP = {
    1: "文本", 3: "图片", 34: "语音", 43: "视频", 47: "表情",
    49: "应用消息", 10000: "系统", 10002: "撤回/系统",
}


def type_name(local_type):
    t = local_type & 0xFFFFFFFF
    return TYPE_MAP.get(t, f"类型{t}")


def main():
    os.makedirs(OUT, exist_ok=True)
    names = load_contacts()
    summary = load_session_summary()
    print(f"联系人 {len(names)} 个，会话摘要 {len(summary)} 条")

    # username -> md5 表名
    md5_to_user = {hashlib.md5(u.encode()).hexdigest(): u for u in names}

    dbs = sorted(f for f in os.listdir(DECRYPTED) if f.startswith("message_message_"))
    stats = {}
    t0 = time.time()

    for db in dbs:
        path = os.path.join(DECRYPTED, db)
        if not os.path.exists(path) or os.path.getsize(path) < 4096 * 4:
            continue
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            con.text_factory = bytes
            tables = [r[0].decode() if isinstance(r[0], bytes) else r[0]
                      for r in con.execute(
                          "select name from sqlite_master where type='table' and name like 'Msg_%'")]
        except sqlite3.DatabaseError as e:
            print(f"  跳过 {db}（{e}）")
            continue
        for t in tables:
            md5 = t[4:]
            user = md5_to_user.get(md5)
            title = names.get(user, user or md5)
            try:
                rows = list(con.execute(
                    f'select local_type, real_sender_id, create_time, message_content '
                    f'from "{t}" order by create_time'))
            except Exception:
                continue
            if not rows:
                continue
            lines = []
            is_room = bool(user and "@chatroom" in user)
            for lt, sid, ts, content in rows:
                txt = to_text(content)
                if not txt.strip():
                    continue
                t = (lt or 0) & 0xFFFFFFFF
                try:
                    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    dt = str(ts)
                who = ""
                if is_room:
                    m = re.match(r"^([^:\n]{5,80}):\n", txt)
                    if m:
                        who = names.get(m.group(1), m.group(1))
                        txt = txt[m.end():]
                if t == 1:
                    body = txt
                elif t == 3:
                    body = "[图片]"
                elif t == 34:
                    body = "[语音]"
                elif t == 43:
                    body = "[视频]"
                elif t == 47:
                    body = "[表情]"
                elif t == 49:
                    mt = re.search(r"<title>(.*?)</title>", txt, re.S)
                    body = "[链接/文件] " + (mt.group(1).strip() if mt else "")
                elif t in (10000, 10002):
                    body = txt
                else:
                    body = f"[{t}]"
                body = body.replace("\n", " ").strip()
                if not body:
                    continue
                who_s = f"{who}：" if who else ""
                lines.append(f"[{dt}] {who_s}{body}")
            if not lines:
                continue
            key = user or md5
            rec = stats.setdefault(key, {"title": title, "user": user, "lines": []})
            rec["lines"].extend(lines)
        con.close()
        print(f"  处理完 {db}（{time.time()-t0:.0f}s）")

    print(f"\n共 {len(stats)} 个会话有消息，开始写文件")
    index = []
    for i, (key, rec) in enumerate(sorted(stats.items(),
                                          key=lambda x: -len(x[1]["lines"]))):
        title = rec["title"] or key
        safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:60]
        is_room = bool(rec["user"] and "@chatroom" in rec["user"])
        sub = "群聊" if is_room else "单聊"
        d = os.path.join(OUT, sub)
        os.makedirs(d, exist_ok=True)
        fn = os.path.join(d, f"{safe}.md")
        n = 1
        while os.path.exists(fn):
            fn = os.path.join(d, f"{safe}_{n}.md")
            n += 1
        with open(fn, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"- 微信标识：`{rec['user'] or key}`\n")
            f.write(f"- 消息条数：{len(rec['lines'])}\n\n---\n\n")
            f.write("\n".join(rec["lines"]))
        index.append({"title": title, "count": len(rec["lines"]),
                      "file": os.path.relpath(fn, BASE), "type": sub,
                      "summary": summary.get(rec["user"] or "", ""),
                      "user": rec["user"] or key})

    json.dump(index, open(os.path.join(BASE, "index.json"), "w"),
              indent=1, ensure_ascii=False)
    total = sum(i["count"] for i in index)
    print(f"完成：{len(index)} 个会话，{total} 条消息，用时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
