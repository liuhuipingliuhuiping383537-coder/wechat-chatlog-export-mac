"""生成微信聊天记录检索首页。"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wxconf

BASE = wxconf.out_base()
index = json.load(open(os.path.join(BASE, "index.json")))
total_msg = sum(i["count"] for i in index)
rooms = sum(1 for i in index if i["type"] == "群聊")
now = datetime.now().strftime("%Y-%m-%d %H:%M")

items = []
for it in index:
    items.append({
        "t": it["title"], "c": it["count"], "f": it["file"],
        "y": it["type"], "s": it.get("summary", ""), "u": it.get("user", ""),
    })

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信聊天记录 · 本地知识库</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
background:#f7f8fa;color:#1f2329}}
header{{background:#fff;border-bottom:1px solid #e5e6eb;padding:24px 32px}}
h1{{margin:0 0 6px;font-size:20px;font-weight:600}}
.sub{{color:#86909c;font-size:13px}}
.stats{{display:flex;gap:28px;margin-top:16px;flex-wrap:wrap}}
.stat{{background:#f2f3f5;border-radius:8px;padding:10px 18px}}
.stat b{{display:block;font-size:22px;color:#1f6feb}}
.stat span{{font-size:12px;color:#86909c}}
.wrap{{max-width:1100px;margin:0 auto;padding:0 32px 60px}}
.search{{margin:20px 0 12px;display:flex;gap:10px}}
input{{flex:1;padding:11px 14px;border:1px solid #dcdfe6;border-radius:8px;font-size:14px;outline:none}}
input:focus{{border-color:#1f6feb}}
select{{padding:11px;border:1px solid #dcdfe6;border-radius:8px;font-size:14px;background:#fff}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;
box-shadow:0 1px 3px rgba(0,0,0,.06)}}
th{{background:#f2f3f5;text-align:left;padding:11px 14px;font-size:12px;color:#4e5969;font-weight:500}}
td{{padding:11px 14px;border-top:1px solid #f0f1f3;font-size:13px;vertical-align:top}}
a{{color:#1f6feb;text-decoration:none}}
a:hover{{text-decoration:underline}}
.tag{{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;margin-right:6px}}
.tag.g{{background:#e8f3ff;color:#1f6feb}}
.tag.p{{background:#e8fff3;color:#00a870}}
.num{{color:#86909c;font-size:12px;white-space:nowrap}}
.sum{{color:#86909c;font-size:12px;max-width:420px;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
tr:hover td{{background:#fafbfc}}
</style>
</head>
<body>
<header>
<h1>微信聊天记录 · 本地知识库</h1>
<div class="sub">导出时间 {now} · 数据全部在本机，未上传任何位置</div>
<div class="stats">
<div class="stat"><b>{total_msg:,}</b><span>条消息</span></div>
<div class="stat"><b>{len(index):,}</b><span>个会话</span></div>
<div class="stat"><b>{rooms:,}</b><span>个群聊</span></div>
<div class="stat"><b>{len(index)-rooms:,}</b><span>个单聊</span></div>
</div>
</header>
<div class="wrap">
<div class="search">
<input id="q" placeholder="搜会话名、备注或最后一条消息…">
<select id="t"><option value="">全部</option><option value="群聊">群聊</option><option value="单聊">单聊</option></select>
</div>
<table>
<thead><tr><th style="width:38%">会话</th><th style="width:80px">消息数</th><th>最后一条消息</th></tr></thead>
<tbody id="tb"></tbody>
</table>
</div>
<script>
const DATA={json.dumps(items, ensure_ascii=False)};
const tb=document.getElementById('tb'),q=document.getElementById('q'),ty=document.getElementById('t');
function render(){{
  const kw=q.value.trim().toLowerCase(), t=ty.value;
  let rows=DATA.filter(d=>{{
    if(t&&d.y!==t) return false;
    if(!kw) return true;
    return (d.t+' '+d.s+' '+d.u).toLowerCase().includes(kw);
  }}).slice(0,300);
  tb.innerHTML=rows.map(d=>`<tr>
   <td><span class="tag ${{d.y==='群聊'?'g':'p'}}">${{d.y}}</span><a href="${{d.f}}" target="_blank">${{d.t}}</a></td>
   <td class="num">${{d.c.toLocaleString()}}</td>
   <td class="sum" title="${{d.s.replace(/"/g,'&quot;')}}">${{d.s||'—'}}</td></tr>`).join('');
  if(!rows.length) tb.innerHTML='<tr><td colspan="3" style="color:#86909c;padding:30px;text-align:center">没有匹配的会话</td></tr>';
}}
q.oninput=render; ty.onchange=render; render();
</script>
</body></html>"""

out = os.path.join(BASE, "微信聊天记录总览.html")
open(out, "w", encoding="utf-8").write(html)
print("生成", out, f"{os.path.getsize(out)/1024/1024:.1f} MB")
