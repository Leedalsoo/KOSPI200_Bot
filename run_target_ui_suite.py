"""Target Architecture - Multi-UI Web Server Suite.

Spawns independent control web servers for:
1. VMS Control UI: http://localhost:8001
2. VSSF Broker UI: http://localhost:8002
3. Option Program UI: http://localhost:8003
"""
import http.server
import socketserver
import threading
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, target_html: str, *args, **kwargs):
        self.target_html = target_html
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            file_path = BASE_DIR / self.target_html
            if file_path.exists():
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
        super().do_GET()

def start_server(port: int, target_html: str, name: str):
    def handler(*args, **kwargs):
        return CustomHandler(target_html, *args, **kwargs)
        
    with socketserver.TCPServer(("", port), handler) as httpd:
        logger.info(f"[{name}] Web Control Panel Serving at http://localhost:{port}")
        httpd.serve_forever()

def launch_ui_suite():
    servers = [
        (8001, "virtual_market_simulator/control/vms_control_panel.html", "VMS Market Simulator UI"),
        (8002, "virtual_securities_firm/control/vssf_control_panel.html", "VSSF Broker Firm UI"),
        (8003, "option_program/control/option_program_control_panel.html", "Option Program Strategy UI")
    ]
    
    threads = []
    for port, html_path, name in servers:
        t = threading.Thread(target=start_server, args=(port, html_path, name), daemon=True)
        t.start()
        threads.append(t)
        
    logger.info("==================================================================")
    logger.info("[Target Architecture] Multi-UI Suite Successfully Launched!")
    logger.info("  * VMS Control UI:            http://localhost:8001")
    logger.info("  * VSSF Broker UI:           http://localhost:8002")
    logger.info("  * Option Program UI:        http://localhost:8003")
    logger.info("==================================================================")
    return threads

if __name__ == "__main__":
    launch_ui_suite()
    import time
    time.sleep(2)
    logger.info("[UI Suite Standby Mode] All 3 UI Control Panels Active.")
