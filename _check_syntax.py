import py_compile
import sys
try:
    py_compile.compile("mock_ws_server.py", doraise=True)
    print("PASS: syntax OK")
except py_compile.PyCompileError as e:
    print("FAIL:", e)
    sys.exit(1)
