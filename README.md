# Wallpaper Changer

一个 Windows 小型壁纸更换器。支持后台预下载壁纸、切换上一张、收藏/取消收藏、收藏夹后台轮播、开机自启动。

[中文使用说明](#环境与安装) · [English](#english) · [GitHub 仓库](https://github.com/huades/wallpaper)

## 环境与安装

- Windows 桌面环境，Python 3.10 或更新版本，并带有 Tkinter（Python 的图形界面库）。
- 只使用 Python 标准库，无需安装第三方依赖。
- 下载新图片需要网络；程序目录需要写入权限，用于保存缓存、收藏与设置。

1. 在 [GitHub 仓库](https://github.com/huades/wallpaper) 点击 **Code → Download ZIP**，解压到一个有写入权限的文件夹；保留 `assets` 目录。
2. 安装 Python，在安装界面勾选 **Add python.exe to PATH**，保留 Tcl/Tk 组件。已有 Anaconda/Python 环境也可使用。
3. 在解压后的项目文件夹打开 PowerShell，检查环境：

   ```powershell
   python --version
   python -c "import tkinter; print('Tkinter OK')"
   ```

4. 双击 `start_wallpaper.bat`，或者在同一文件夹运行：

   ```powershell
   python main.py
   ```

出现带有分类、轮播时间和按钮的小窗口即启动成功。

## 启动

双击：

```text
start_wallpaper.bat
```

脚本会优先使用：

```text
D:\Anaconda3\pythonw.exe
```

脚本先检查本机 `D:\Anaconda3`，再查找 PATH 中的 `pythonw` 或 `python`。使用 `pythonw` 时，启动命令行窗口会退出；如果回退到 `python`，控制台可能保留以显示错误。没有安装在该路径也可以使用，无需修改脚本，只需确保 Python 已加入 PATH。

## 使用步骤

1. 选择分类，等待后台预下载；再次启动会恢复上次分类。
2. 点击 `▶` 查看缓存图片并设置壁纸，喜欢的点击 `❤` 收藏，再点一次取消收藏。
3. 收藏至少一张后点击 `🎞` 开启收藏轮播，选择轮播间隔；关闭主窗口后后台轮播仍会继续。
4. 轮播模式下，上下张和取消收藏作用于收藏夹；手动切图会重置轮播倒计时。取消收藏后立即切换下一张；收藏夹为空时停止轮播。
5. 点击 `⚙` 调整缓存上限和透明度。停止轮播时，重新打开主窗口并点击 `🎞`。

## 功能

- `◀ 上一张`：切换回本次运行中上一张壁纸。
- `▶ 下一张`：从当前分类的预下载缓存取图，并以渐变反馈设置为桌面壁纸。
- `❤ 收藏/取消`：第一次点击收藏当前壁纸，再次点击取消收藏。
- `🎞 收藏轮播`：后台轮播 `favorites` 文件夹里的收藏壁纸，可选 `10/20/30/45秒` 和 `1/3/5/10分钟`，默认 10 秒切换一次，关闭对话框后仍会继续执行。
- `🚀 开机启动`：开启或关闭当前用户的开机自动启动。
- `⚙ 设置`：手动输入预下载缓存大小，范围 `10-1024MB`，默认 `100MB`；调整窗口透明度，范围 `0-70%`，默认 `30%`；也可以打开缓存文件夹。
- `✖ 清已浏览`：不关闭窗口，只删除本次已预览但未收藏的缓存图片。

界面采用紧凑布局：分类和轮播时间在同一行，按钮为一排小工具按钮。

标题右侧的 GitHub 图标打开本项目仓库；悬停或键盘聚焦时显示名称。

## 打开设置与调整透明度

1. 启动程序后，点击主窗口按钮栏最右侧的 `⚙`（下方标注“设置”），设置弹窗会在主窗口中央打开。
2. 拖动“窗口透明度”滑块，主窗口与设置弹窗会立即预览效果。`0%` 表示完全不透明。
3. 点击“确定”保存，重启程序后仍使用保存的透明度。点击“关闭”、右上角关闭按钮或按 Esc，放弃本次修改。
4. 关闭设置弹窗后，再次点击主窗口的 `⚙` 即可重新打开。如果主窗口也已关闭，双击 `start_wallpaper.bat` 启动后再点 `⚙`。

## 分类

当前支持：

```text
随机、自然风光、城市建筑、动物、极简、科技、汽车、动漫、人物
```

首次启动分类是 `随机`，之后恢复上次选择。

优先从 wallhaven 下载；如果不可用，会自动尝试 Bing 每日壁纸和 picsum 备用源。

下载图片后、写入缓存前，会检查 `download_history.json` 以及 `favorites`、`prefetch` 中已有图片的内容哈希（根据图片内容计算的标识），重复内容会跳过保存。未收藏图片删除后仍保留记录；历史最多保留 180 天、5000 条，超出保留范围的旧图片可能再次出现。这个检查避免重复入库，但不能保证完全不发生重复网络下载。

## 文件夹

界面使用 Tkinter，图片下载使用 `urllib`，Windows 壁纸与开机启动使用系统 API 和当前用户注册表。

- `main.py`：主窗口、缓存管理与后台轮播。
- `start_wallpaper.bat`：Windows 启动入口。
- `assets/github-mark.png`：来自 [GitHub 官方资源](https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png)的仓库图标。

- `prefetch`：按分类保存后台预下载图片；未预览图片会保留，已预览未收藏图片关闭时删除。
- `favorites`：收藏目录。收藏的图片会保留，也会用于后台轮播。
- `prefetch_state.json`：预下载缓存状态。
- `settings.json`：缓存大小、上次分类及窗口透明度设置，默认 `100MB`、`随机` 和 `30%`。
- `slideshow.log`：后台轮播错误日志。
- `.slideshow_state.json`：当前收藏轮播图片状态。

缓存、收藏、个人设置、下载历史和轮播运行文件已被 `.gitignore` 排除，不随源码上传。设置通过 `⚙` 修改，无需编辑配置文件；默认缓存为 `100MB`、透明度 `30%`、轮播间隔 `10秒`。

## 常见问题

如果点击下一张提示缓存为空，通常是后台还在补图，稍等后再点即可。程序会自动尝试 wallhaven、Bing 每日壁纸和 picsum 备用源；如果一直无法补图，请检查网络、代理或防火墙。

如果要停止后台轮播，重新打开程序后点击 `🎞 收藏轮播` 按钮即可停止。

开启收藏轮播后，`◀`、`▶`、`❤` 都只作用于收藏夹图片；这时 `▶` 不会下载新图，而是切换到下一张已收藏壁纸。

缓存达到上限时，当前分类如果没有未预览缓存，会按顺序腾空间：先删当前分类最早的已预览未收藏图，再删其他分类最早的已预览未收藏图，最后才删其他分类中超过 3 张保底的最旧未预览未收藏图。收藏图和当前正在显示的图不会删除。

后台补图会先让每个分类保留至少 3 张未预览缓存；全部达标后，再优先给当前分类补图直到缓存上限。切换分类时会保存新分类，下次启动自动恢复，并立即删除其他分类已预览未收藏的缓存图。

可能增长的运行文件：`prefetch` 受设置的缓存上限控制；`download_history.json` 用于避免重复下载，自动保留最近 180 天且最多 5000 条记录；`prefetch_state.json` 会随缓存增删变化；`slideshow.log` 超过 1MB 会自动清空。

双击启动后没有窗口时，在项目文件夹执行 `python main.py` 查看错误。如果提示缺少 Tkinter，请重新安装带 Tcl/Tk 的 Python；如果提示找不到图标，请确认解压时保留了 `assets` 文件夹。壁纸源可用性与实际分类结果取决于上游服务，备用源未必严格匹配所选分类。

## English

Wallpaper Changer is a compact Windows desktop app built with Python's standard library and Tkinter. It predownloads wallpapers into category caches, saves favorites, runs a background favorites slideshow, supports startup at sign-in, and offers adjustable window transparency.

### Requirements and Installation

Use Windows and Python 3.10+ with Tcl/Tk. No third-party packages are required. Downloads need internet access, and the project directory must be writable.

1. Download **Code → Download ZIP** from [this repository](https://github.com/huades/wallpaper) and extract it, keeping the `assets` directory.
2. Install Python with **Add python.exe to PATH** and Tcl/Tk enabled.
3. Open PowerShell in the extracted project directory and run:

   ```powershell
   python --version
   python -c "import tkinter; print('Tkinter OK')"
   python main.py
   ```

The small window with category selectors and buttons confirms startup. You can also double-click `start_wallpaper.bat`. The launcher checks `D:\Anaconda3` before searching PATH. It uses `pythonw` when available; the `python` fallback may keep a console open for diagnostics.

### Use and Configuration

Choose a category, wait for background prefetching, then use Next to apply a cached wallpaper. Previous returns through session history. Favorite toggles the current image's saved copy. Categories include random, landscapes, architecture, animals, minimalism, technology, cars, anime, and people; the last category is restored on launch.

With at least one favorite, enable the slideshow and select 10/20/30/45 seconds or 1/3/5/10 minutes. During slideshow mode, navigation and unfavoriting operate on favorites; manual changes reset the timer, and unfavoriting advances immediately. Closing the main window leaves the slideshow running. Reopen the app and toggle the slideshow button to stop it. The startup button toggles launch at Windows sign-in.

Click the gear button to open Settings at the center of the main window. Cache size is 10–1024 MB (default 100 MB). Transparency is 0–70% (default 30%; 0% is opaque). Drag the slider for a live preview, then click Confirm to save. Close or Esc discards changes. Click the gear again to reopen Settings; it also offers an Open Folder button. The header's GitHub icon opens this repository and has a hover/focus label.

`main.py` implements the app, `start_wallpaper.bat` launches it, and `assets` contains the repository icon. Runtime files include `prefetch/`, `favorites/`, `settings.json`, `prefetch_state.json`, `download_history.json`, `.slideshow_state.json`, and `slideshow.log`. They are ignored by Git. Viewed, unfavorited session cache images are removed on window close or by the Clear Viewed button; unviewed caches and favorites remain.

Prefetching aims to keep three unviewed images per category before filling the active category, subject to the cache budget. Switching categories clears viewed, unfavorited caches in other categories. When full and the active category has no unviewed image, eviction tries viewed images first, then older unviewed images in other categories above their three-image reserve. Favorites and the current image are protected in these eviction paths. Hash history retains up to 5,000 entries for 180 days; it prevents duplicate storage within that history, but may still require downloading an image to compare its content. Logs over 1 MB are cleared at app startup.

### Troubleshooting

An empty-cache message means background prefetching is still running or a source failed. Check network/proxy/firewall access. Downloads try Wallhaven, Bing, then Picsum; fallback sources may not match the selected category. If the launcher produces no window, run `python main.py` to read the error. Missing Tkinter requires a Python installation with Tcl/Tk; a missing icon requires the `assets` directory to be restored.
