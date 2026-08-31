# 更新日志

本文件记录 douyin-bot 的重要变更。日期格式 YYYY-MM-DD。

## 2026-08-31

### X 链路修复：分类走 FxTwitter API + 截图走有头浏览器（输出形态与原版一致）

**背景（两个都是 X 侧变更，实测确认）：**
1. X 对 headless 浏览器一律返回 HTTP 403 空白页——带不带登录 cookie、换任意 UA、
   连真 Chrome 的 headless 模式都被拦；有头模式正常。导致截图出来是纯白图。
2. X 页面已把 `data-testid` 属性全部删光（整页查到 0 个），原来靠
   `article[data-testid="tweet"]`/`twitterArticleRichTextView` 的 DOM 分类全部失配。
3. 另实测 syndication API 的 `note_tweet.text` 已被掏空（字段在但正文为空），
   只能继续当"是否长推"的布尔探测用。

**变更：**
- 新增 `fx_twitter.py`：走 FxTwitter 公共解析 API（`api.fxtwitter.com/i/status/<id>`），
  无需浏览器和 cookie。长推（NoteTweet）`text` 即完整全文；X 文章标题/正文取
  `article.title` + `article.content.blocks`（实测拿到 6600 字全文+封面图）；
  引用推取 `quote` 全文；图片取 `media.photos` 直链下载
- `_process_article`：X 链接的 kind/标题/正文/引用/图改由 `fetch_x_content` 提供
  （FxTwitter 失败时回退原 Playwright 提取）；截图/搬运的判定阈值与输出形态不变
  （x_article 与超 1000 字 → 截图+标题+链接；短内容 → 文本搬运+图）
- `webpage_screenshot` / `extract_page_content`：X 页面改用有头浏览器
  （`headless=False` + 窗口移到屏幕外 `--window-position=-32000,-32000`），
  绕过 403；非 X 平台仍 headless
- `_process` X 视频路径：长推全文改用 `fx_twitter.fetch_full_text`，替代原
  `x_long_tweet.fetch_full_tweet_text`（Playwright headless，已失效）
- `x_long_tweet.py` 保留：`_load_x_cookies` 仍被截图链路复用

**行为变化：** 对用户无感——X 文章/长推仍是截图+原图+标题+链接，短推仍是文本搬运。
唯一区别：处理 X 链接时后台会开一个屏幕外的浏览器窗口（Dock 可能闪一下图标）。

### X 截图改逐屏滚动截图，弃用 full_page（同日追加，修复长文重复）

用户实测：文章一长（3 段以上）截图内容又出现重复。根因是 `full_page=True`——
Chromium 整页截图会把视口拉伸成整页高度，触发 X（React 虚拟化渲染）重新布局，
内容位置漂移后切出来的分段就会重复/错位；短文章不触发所以之前测不出来。

修复（`webpage_screenshot`，仅 X）：
- 弃用 full_page，改回逐屏滚动截图：视口始终 700×1600 不变，X 按正常浏览渲染，
  每段所见即所得；每段按「目标区间 − 实际 window.scrollY」用 PIL 精裁，
  底部滚动钳制也不会重叠/遗漏（有效高度 <40px 的碎段直接丢弃）
- 截图前一次性清场：删除所有 fixed/sticky 元素（顶部悬浮条/cookie 框，
  逐屏截图时会盖在每段顶部）+ 摘除正文中的登录拦截卡 + 重新量主文 bottom 为终点
- 非 X 平台保持原有 full_page + PIL 切分不变
- 实测（6600 字文章）：两段首尾句子无缝相连，零重叠零遗漏零遮挡

### X 截图只保留主文：裁掉评论区 + 摘除登录拦截卡 + 不再附原图（同日追加）

用户反馈截图"重复且有遮挡"，实测三个问题：
1. 文章封面图在截图里已有，尾部又附同一张原图 → 同图两遍
2. "See all the replies / Continue to X" 登录拦截卡嵌在正文中间遮挡内容
   （不含 cookie/log in 关键词，悬浮层清除规则抓不到；且它不是 fixed 定位）
3. 截图段落包含评论区和加载骨架（全是垃圾内容）

修复（`webpage_screenshot`，仅 X 生效）：
- 主文边界用页面第一个 `<article>` 元素（testid 删光后普通标签仍在）：
  截图裁切到 `article.bottom` 为止，评论区/推荐内容全部不进截图
- 截图前从 DOM 摘除 "See all the replies"/"Continue to X" 拦截卡
  （从命中文本向上爬到整卡容器再删；高度>400px 或文本>200 字判为爬过头）
- X 不再下载/附加内容原图（截图分段已含全部配图）；非 X 平台原图逻辑不变
- 教训：第一版裁在拦截卡的 Y 坐标上，而拦截卡嵌在正文中间，误裁掉文章后半段；
  裁切线必须用主文元素的 bottom，不能用拦截卡位置

### 修复相册乱序/"重复"：截图分段在前、原图在后（同日追加）

`webpage_screenshot` 原先把文章原图先放进列表，多段截图 append 在其后，
相册发出去是「原图们+截图段们」——原图夹在前面，和截图里的同款图混在一起，
看起来乱序且重复（单段分支是 `insert(0)` 反而正确，所以内容短时从未暴露）。
现在返回顺序固定为：截图分段 1..N 在前，原图在后。

### 截图去 cookie 弹窗遮挡（同日追加）

testid 删光的连带后果：旧的按 `data-testid` 隐藏弹窗的 CSS 全部失配，
"Did someone say … cookies?" 同意弹窗（fixed 700×254）露出来挡在截图上。
新增 `X_OVERLAY_CLEANUP_JS`：按 fixed/sticky 定位 + cookie/log in/sign up 关键词
删除悬浮层（文本超 600 字不删，防误删整页容器），在页面加载后和截图前各执行一次
（滚动懒加载可能让弹窗重新挂载）。实测清除后无残留、截图分段全有内容。

## 2026-05-14 ~ 05-19

### X 长推文（NoteTweet）全文提取（2026-05-19）

新增 `x_long_tweet.py`：
- `is_long_tweet()` 通过 X syndication API 探测推文是否带 `note_tweet` 字段（X Premium 长推标志）
- `fetch_full_tweet_text()` 用 Playwright 加载推文页 → 点击"Show more"展开 → 提取 `tweetText` innerText，并把 a 标签替换为展开 URL

`_process` 在 X 路径里：yt-dlp 拿完 description 后再探测长推，是长推就用 Playwright 抓的全文覆盖 title。
原因：yt-dlp 的 X extractor 只返回 ~280 字，长推被截断（实测从 159 字提升到 298 字）。

### 纯视频平台失败时静默（2026-05-18）

YouTube / Bilibili / Instagram / 快手 / 小红书 这类纯视频站点，下载失败时不再响应任何错误消息或截图，直接静默跳过。
原因：这些站点没有"图文推文"形态，下载失败基本意味着原视频被删/区域限制/付费墙，截图也没意义。
保留的兜底逻辑：X / weibo / 腾讯新闻等带文字内容的站点，视频失败时仍走截图。

### 腾讯新闻视频下载（2026-05-17）

新增 `qq_news_extractor.py`：用 Playwright 拦截页面里的 m3u8 流，再用 ffmpeg 转封装为 mp4。
- 触发：`news.qq.com` / `view.inews.qq.com`
- 流程：访问页面 → 拦截首个 m3u8 请求（最多等 6 秒）→ ffmpeg `-c copy` 转 mp4
- 失败兜底：拦截不到 m3u8 或 ffmpeg 报错 → 自动回退到截图

原因：yt-dlp 不支持腾讯新闻（页面视频是 JS 动态加载的 blob），且 yt-dlp 的 vqq:video extractor 当前被腾讯反爬限制。

### 未知链接智能分流（2026-05-17）

未知链接（不在 PLATFORMS 列表）的处理逻辑改为：
1. 白名单文章平台（X/微博/微信公众号/知乎/Medium/Substack）→ 直接截图
2. 其他链接 → 用 `yt-dlp --simulate` 探测 10 秒
   - 探测到视频 → 走视频下载流程
   - 没有视频或超时 → 截图
3. 视频下载失败 → 自动回退到截图（之前只对 X/weibo 兜底，现扩展到所有平台）

### 口令控制

消息里可在链接前后任意位置加口令：

- `/skip` 或 `跳过` → 直接忽略，不处理
- `/title` 或 `标题` → 只发视频+标题，跳过 whisper
- `/text` 或 `文案` → 只提取文案，不发视频

### 启动通知

bot 启动时自动给 BOT_OWNER 发一条启动消息，列出支持的口令。新增 `BOT_OWNER` 环境变量（不填则取 ALLOWED_USERS 最小值）。

### whisper 幻觉处理升级

- `clean_hallucination` 新增全局占比检测：幻觉行超过 50% 或超过 20 行直接返回空，解决从头就乱的情况（之前只裁尾部）
- 新增常见幻觉短语黑名单（"优优独播剧场"、"字幕志愿者"等）

### whisper 前置试探扩展到所有平台

之前只有 X/Twitter 才截前 10 秒试探，现在所有平台统一截前 15 秒跑 whisper，不连贯直接跳过全程转录，节省时间。

### 文章链接逻辑收紧

`is_article_url` 改为白名单逻辑，只有明确列出的文章平台（twitter.com、x.com、weibo.com 等）才走截图流程，其余未知链接一律忽略不响应。

### github.com 加入平台列表

github.com 链接现在走文章截图流程（之前因不在平台列表被当作未知链接处理）。

## 2026-04-29

### 仓库可直接 clone 启动

- 新增 `run.sh`（启动脚本，加载 `.env` 后跑 bot.py）入库
- 新增 `.env.example`（环境变量模板）入库
- `.gitignore` 追加 `*.log`（避免 `bot.log` 入库）
- README.md 启动章节改写：从「编辑 bot.py 填值 + python3 bot.py」改为「复制 .env.example → .env 填值 + ./run.sh」，与代码实际行为一致

### 白名单扩展：支持多用户 + 多群组

**变更：** 把白名单从「单用户 + 单群」改成「多用户 + 多群」，配置项继续叫 `ALLOWED_USER` / `ALLOWED_GROUP`，但值用逗号分隔。

**.env：** `ALLOWED_USER` 扩展为多个用户 ID（逗号分隔），`ALLOWED_GROUP` 扩展为多个群 ID（逗号分隔）。具体值见本地 `.env`（不入库）。

**bot.py：**
- `ALLOWED_USER` → `ALLOWED_USERS`（set），`ALLOWED_GROUP` → `ALLOWED_GROUPS`（set）
- 白名单判断改为 `chat_id not in ALLOWED_GROUPS and user.id not in ALLOWED_USERS`

**README.md：** 同步说明配置项现支持逗号分隔多个 ID。

**注意事项：**
- 改完后需重启 bot 进程才生效
- Telegram 每个 bot token 只允许一个 `getUpdates` 轮询客户端，重启时务必先停旧进程，避免双开导致 `Conflict: terminated by other getUpdates request` 报错
