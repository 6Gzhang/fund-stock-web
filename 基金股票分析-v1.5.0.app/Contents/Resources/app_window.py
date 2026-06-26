"""
基金股票分析软件 - 独立窗口（基于 tkinterweb）
"""
import os
import sys
import time
import threading
import webbrowser
import traceback

LOG_FILE = os.path.expanduser("~/Library/Logs/FundStockApp_window.log")

def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

log("=" * 50)
log("窗口程序启动")
log(f"Python: {sys.executable}")
log(f"Python version: {sys.version}")

try:
    import tkinter as tk
    log("tkinter 导入成功")
except Exception as e:
    log(f"tkinter 导入失败: {e}")
    log(traceback.format_exc())
    sys.exit(1)

try:
    from tkinterweb import HtmlFrame
    log("tkinterweb 导入成功")
except Exception as e:
    log(f"tkinterweb 导入失败: {e}")
    log(traceback.format_exc())
    sys.exit(1)


APP_TITLE = "基金股票分析软件"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
PORT = 8080
CHECK_INTERVAL = 0.5


class StockApp:
    def __init__(self):
        log("初始化 StockApp")
        try:
            self.root = tk.Tk()
            log("Tk root 创建成功")
        except Exception as e:
            log(f"Tk root 创建失败: {e}")
            log(traceback.format_exc())
            raise

        try:
            self.root.title(APP_TITLE)
            self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
            self.root.minsize(1000, 600)
            self.root.configure(bg="#0a0e1a")

            try:
                self.root.iconname(APP_TITLE)
            except Exception:
                pass

            self._setup_ui()
            self.root.protocol("WM_DELETE_WINDOW", self.on_close)
            log("UI 设置完成")

            self._wait_and_load()
            log("开始等待后端并加载")
        except Exception as e:
            log(f"初始化失败: {e}")
            log(traceback.format_exc())
            raise

    def _setup_ui(self):
        try:
            self.frame = HtmlFrame(
                self.root,
                messages_enabled=False,
            )
            self.frame.pack(fill=tk.BOTH, expand=True)
            log("HtmlFrame 创建成功")
        except Exception as e:
            log(f"HtmlFrame 创建失败: {e}")
            log(traceback.format_exc())
            raise

        try:
            self.frame.on_link_click(self._on_link_click)
        except Exception:
            pass

        self._show_loading()

    def _show_loading(self):
        loading_html = """
        <html>
        <head>
            <style>
                body {
                    margin: 0; padding: 0;
                    display: flex; justify-content: center; align-items: center;
                    height: 100vh; background: #0f1320;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
                }
                .loading-container { text-align: center; color: #fff; }
                .spinner {
                    width: 48px; height: 48px;
                    border: 4px solid rgba(255,255,255,0.1);
                    border-top-color: #4f8cff;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 24px;
                }
                @keyframes spin { to { transform: rotate(360deg); } }
                .loading-text { font-size: 18px; color: #c5c9d9; margin-bottom: 8px; }
                .loading-sub { font-size: 13px; color: #5c6072; }
            </style>
        </head>
        <body>
            <div class="loading-container">
                <div class="spinner"></div>
                <div class="loading-text">正在加载行情数据...</div>
                <div class="loading-sub">首次加载可能需要几秒钟</div>
            </div>
        </body>
        </html>
        """
        try:
            self.frame.load_html(loading_html)
        except Exception as e:
            log(f"加载 loading HTML 失败: {e}")

    def _wait_and_load(self):
        import urllib.request

        def _check():
            log("开始检查后端服务")
            for i in range(120):
                try:
                    req = urllib.request.Request(f"http://localhost:{PORT}/api/version")
                    resp = urllib.request.urlopen(req, timeout=2)
                    if resp.status == 200:
                        log(f"后端服务就绪（第{i}次检查）")
                        time.sleep(1)
                        self.root.after(0, self._load_app)
                        return
                except Exception as e:
                    if i % 10 == 0:
                        log(f"第{i}次检查失败: {e}")
                time.sleep(CHECK_INTERVAL)
            log("后端服务检查超时，直接加载")
            self.root.after(0, self._load_app)

        threading.Thread(target=_check, daemon=True).start()

    def _load_app(self):
        log("加载应用页面")
        try:
            self.frame.load_url(f"http://localhost:{PORT}/")
            log("页面加载命令已发送")
        except Exception as e:
            log(f"页面加载失败: {e}")
            log(traceback.format_exc())

    def _on_link_click(self, url):
        if url and url.startswith("http") and "localhost" not in url:
            webbrowser.open(url)
            return "ignore"
        return None

    def on_close(self):
        log("窗口关闭")
        try:
            self.root.destroy()
        except Exception as e:
            log(f"窗口销毁失败: {e}")

    def run(self):
        log("进入主循环")
        try:
            self.root.mainloop()
        except Exception as e:
            log(f"主循环异常: {e}")
            log(traceback.format_exc())
        log("主循环退出")


if __name__ == "__main__":
    try:
        app = StockApp()
        app.run()
    except Exception as e:
        log(f"程序异常退出: {e}")
        log(traceback.format_exc())
        sys.exit(1)
