"""在微信启动过程中 attach 并 hook CCKeyDerivationPBKDF（root 运行，自动等进程出现）。"""
import frida
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wxconf

OUT = str(wxconf.TMP / "pbkdf_hits.jsonl")
TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 60

JS = """
var seen = {};
var target = null;
try { target = Module.findGlobalExportByName("CCKeyDerivationPBKDF"); } catch (e) {}
send({type: "info", found: target !== null});
if (target) {
  Interceptor.attach(target, {
    onEnter(args) {
      var pwLen = args[2].toInt32();
      var saltLen = args[4].toInt32();
      var dkLen = -1;
      try { dkLen = args[8].toInt32(); } catch (e) {}
      var key = pwLen + ":" + hex(args[1], Math.min(pwLen, 64));
      if (!seen[key]) {
        seen[key] = 1;
        send({type: "cckey", pwLen: pwLen, saltLen: saltLen, prf: args[5].toInt32(),
              rounds: args[6].toInt32(), dkLen: dkLen,
              pw: hex(args[1], Math.min(pwLen, 64)),
              salt: hex(args[3], Math.min(saltLen > 0 ? saltLen : 16, 32))});
      }
      this.dk = args[7];
      this.dkLen = dkLen;
    },
    onLeave(retval) {
      try {
        if (this.dk && this.dkLen > 0) {
          send({type: "dk", dkLen: this.dkLen, dk: hex(this.dk, Math.min(this.dkLen, 64))});
        }
      } catch (e) {}
    }
  });
}
function hex(ptr, n) {
  if (!ptr || ptr.isNull() || n <= 0) return "";
  var v = new Uint8Array(ptr.readByteArray(n));
  var out = [];
  for (var i = 0; i < v.length; i++) out.push(('0' + v[i].toString(16)).slice(-2));
  return out.join('');
}
"""


def main():
    os.makedirs(wxconf.TMP, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    hits = []
    print("[*] 预热 frida...", flush=True)
    frida.get_local_device()
    print("[*] 就绪", flush=True)

    def on_msg(msg, data):
        if msg.get("type") == "send":
            p = msg["payload"]
            with open(OUT, "a") as f:
                f.write(json.dumps(p) + "\n")
            print("[MSG]", json.dumps(p)[:200], flush=True)
            if p.get("type") == "cckey":
                hits.append(p)
        elif msg.get("type") == "error":
            print("[ERR]", str(msg.get("description"))[:200], flush=True)

    t0 = time.time()
    session = None
    pid = None
    forced = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    while time.time() - t0 < 40:
        if forced:
            cands = [forced]
            forced = 0
        else:
            ps = subprocess.run(["ps", "-ax", "-o", "pid=,stat=,command="],
                                capture_output=True, text=True).stdout
            cands = []
            for line in ps.splitlines():
                line = line.strip()
                if "WeChat.app/Contents/MacOS/WeChat" not in line:
                    continue
                parts = line.split(None, 2)
                if len(parts) < 3:
                    continue
                try:
                    pidv = int(parts[0])
                except ValueError:
                    continue
                st = parts[1]
                if "U" in st or "E" in st:   # 跳过卡死/正在退出的进程
                    continue
                cands.append(pidv)
            cands.sort(reverse=True)          # 优先最新的进程
        for p in cands:
            try:
                session = frida.attach(p)
                pid = p
                print(f"[+] attach 成功 pid={p}（用时 {time.time()-t0:.1f}s）", flush=True)
                break
            except Exception as e:
                print(f"[.] pid={p} attach 失败: {str(e)[:60]}", flush=True)
        if session:
            break
        time.sleep(0.15)

    if not session:
        print("[!] 没 attach 上微信")
        sys.exit(1)

    script = session.create_script(JS)
    script.on("message", on_msg)
    script.load()
    print(f"[*] hook 已注入，收集 {TOTAL} 秒", flush=True)

    try:
        end = time.time() + TOTAL
        while time.time() < end:
            time.sleep(2)
            if len(hits) >= 3:
                break
    finally:
        # 必须 detach，否则微信进程会被挂起，变成"卡死"状态
        try:
            script.unload()
        except Exception:
            pass
        session.detach()
        print("[*] 已 detach，微信恢复正常运行", flush=True)

    print(f"[*] 捕获 {len(hits)} 条", flush=True)


if __name__ == "__main__":
    main()
