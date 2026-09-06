# macOS 微信聊天记录全量导出

把 macOS 个人微信（4.x）的**全部**聊天记录解密并导出成本地 Markdown 知识库。
全程在本机完成，不联网、不上传。实测 110 万条消息约 2 分钟导出完。

> 实测环境：macOS + 微信 4.1.11（Apple Silicon）。

## 能做什么

- 导出**所有**单聊和群聊（不是一个一个选）
- 每个会话一个 `.md` 文件，按时间排列
- 生成一个可搜索的 HTML 检索首页
- **一次搭好，密钥永久可用**；以后增量导出只要 1 分钟，不用再折腾微信

## 作为 WorkBuddy 技能使用（推荐）

这个仓库本身就是一个 WorkBuddy 技能包。装好后你只需要说一句
**「导出我的微信聊天记录」**，AI 会照着 `SKILL.md` 一步步跑完，不用自己记命令。

```bash
git clone https://github.com/<你的用户名>/wechat-chatlog-export-mac.git \
  ~/.workbuddy/skills/微信聊天记录全量导出Mac
```

也可以在 WorkBuddy 的技能面板里用 zip 导入整个目录。

### 需要你本人在场的部分

脚本能自动化的都自动化了，但有 3 步触碰系统安全边界，**必须你手动确认**：

| 步骤 | 你要做什么 | 耗时 |
|---|---|---|
| 重签名微信 | 弹窗输一次开机密码 | 2 分钟 |
| 抓密钥 | 弹窗再输一次密码（frida 需要 root） | 1 分钟 |
| 重启微信 | 打开重签名版微信并登录（如果没登录） | 1 分钟 |

其余全程自动。**第一次大约 15–30 分钟**（含下载依赖），
熟练后重跑只要 5 分钟；之后增量导出 1 分钟。

### 前提

- macOS（Apple Silicon / Intel 都行）
- 微信 4.x，且这台 Mac 上登录过、本地有聊天数据
- **Windows 不适用**（本项目的内存读取用的是 macOS 的 frida 方案）

## 快速开始

```bash
pip install -r requirements.txt
```

### 第 1 步：重签名微信（约 5 分钟）

macOS 微信是 hardened 应用，系统禁止其他进程读它的内存。所以要复制一份并注入调试权限。

```bash
mkdir -p ~/Applications
cp -R /Applications/WeChat.app ~/Applications/

# 导出原始授权文件
codesign -d --entitlements :- /Applications/WeChat.app > ~/wx_ent_orig.plist

# 生成带 get-task-allow 的新授权文件
python scripts/make_ent.py

codesign --force --deep --sign - --entitlements ~/wx_ent.plist ~/Applications/WeChat.app
```

**关键**：`make_ent.py` 必须**保留 `com.apple.security.app-sandbox`**。
删掉它微信会切换到另一个数据目录，就读不到你已经有的聊天记录了。只删 `application-identifier` / `team-identifier`。

### 第 2 步：抓密钥（最难，约 10 分钟）

用 [frida](https://frida.re) 在**微信启动的瞬间**拦截系统函数 `CCKeyDerivationPBKDF`：

```bash
mkdir -p /tmp/wxdb

# 1) 后台启动钩子（需要 root，会自动等微信出现）
osascript -e 'do shell script "sh -c \"/usr/bin/python3 -u scripts/auto_attach_hook.py 100 > /tmp/wxdb/hook.log 2>&1 &\"" with administrator privileges'

# 2) 立刻重启微信（必须是 ~/Applications 下的重签名版）
pkill -9 -x WeChat; sleep 2; open ~/Applications/WeChat.app

# 3) 等 45 秒，然后派生并校验全部库密钥
python scripts/derive_all.py
```

三个必须注意的点：

- **必须在启动瞬间 attach**。微信跑起来之后就不再调用 PBKDF2（数据库已经打开了），抓不到。
- **必须 `session.detach()`**。不 detach 会把微信挂成僵尸进程，`kill -9` 都杀不掉。
- frida 17.x 要用 `Module.findGlobalExportByName`，`Module.findExportByName(null, ...)` 会报 "not a function"。

抓到的 `rounds=256000` 那次调用的第二个参数就是 **passphrase**（32 字节），用它派生所有库密钥：

```
enc_key = PBKDF2-HMAC-SHA512(passphrase, db_salt, 256000, 32)
```

只要不换微信号登录，passphrase 就一直有效。

### 第 3 步：解密 + 提取 + 建索引

```bash
python scripts/extract_salts.py     # 读所有 db 首页的 salt
python scripts/decrypt_db.py        # 解密（自动跳过 media_* 缓存库）
python scripts/extract_all.py       # 提取消息 -> chats/
python scripts/build_index.py       # 生成检索首页
```

默认输出到 `~/wechat-export/`：

```
~/wechat-export/
├── chats/
│   ├── 单聊/
│   └── 群聊/
├── _解密库/
├── index.json
└── 微信聊天记录总览.html      <- 打开这个就能搜索全部会话
```

想换目录就设环境变量：

```bash
export WX_OUT_DIR=/path/to/你想要的目录
```

## 以后增量导出

密钥已经有了，一条命令搞定，不用再动微信：

```bash
python scripts/decrypt_db.py && python scripts/extract_all.py && python scripts/build_index.py
```

## 环境变量

| 变量 | 用途 | 默认 |
|---|---|---|
| `WX_OUT_DIR` | 导出结果目录 | `~/wechat-export` |
| `WX_DB_DIR` | 微信 `db_storage` 目录 | 自动查找 |
| `WX_UID` | 多账号时指定账号目录名 | 取体积最大的那个 |
| `WX_KEYS` | 密钥文件路径 | `/tmp/wxdb/all_keys.json` |

## 踩过的坑

| 坑 | 解法 |
|---|---|
| root 反而读不了微信数据目录（TCC） | 读文件用**普通用户**进程，读内存才用 root |
| 沙箱/受限终端里 `sudo` 被禁 | 用 `osascript -e 'do shell script "..." with administrator privileges'` 弹窗提权 |
| `frida.spawn` 被系统杀（信号 137） | 只能用 attach 模式，配合"先后台起钩子再 open 微信" |
| 想在内存里搜 salt 来定位密钥 | **行不通**，密钥不在 salt 附近 ±4KB 内 |
| `com.Tencent.WCDB.Config.Cipher` | Mac 版不存在，只有 Tokenize / ScalarFunction |
| `mach_vm_region_recurse` 结构体坑 | 改用 `vmmap -interleaved <pid>` 输出解析 |
| `text_factory=bytes` 后表名也变 bytes | 表名要 `.decode()` 再拼 SQL |
| 微信被系统/用户切回原版 | 每次操作前确认跑的是 `~/Applications/WeChat.app` |

## 技术细节

### 数据库加密格式（实测）

- 页大小 4096，AES-256-CBC
- page 1：`[0:16] salt` | `[16:4016] 密文` | `[4016:4032] IV` | `[4032:4096] HMAC-SHA512`
- page N：`[0:4016] 密文` | `[4016:4032] IV` | `[4032:4096] HMAC-SHA512`
- 解密后 page 1 的前 16 字节要还原成 `SQLite format 3\0`
- 校验方式：`mac_salt = salt XOR 0x3A`，`mac_key = PBKDF2-HMAC-SHA512(enc_key, mac_salt, 2, 32)`，
  HMAC-SHA512 覆盖 `[16:4032]`，结果存在 `[4032:4096]`

### 消息提取要点

- 表名是 `Msg_<md5(username)>`
- `local_type` 要取低 32 位（高 32 位是别的标记）
- `message_content` 可能是 zstd 压缩（magic `28 b5 2f fd`）
- 群消息正文前缀 `wxid_xxx:\n` 是发送者，要用 contact 表换成昵称
- 图片/视频别吐 XML，直接写 `[图片]` `[视频]`；类型 49 取 `<title>`

## 依赖

```
frida
pycryptodome
zstandard
```

## 免责声明

本项目只用于**导出你自己的微信聊天记录**，属于个人数据可携带的范畴。
导出的内容包含你和联系人的隐私，**请勿公开传播**。
请在遵守当地法律和微信用户协议的前提下使用。
