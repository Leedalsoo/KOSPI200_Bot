import re

with open('mock_ws_server.py', 'r', encoding='utf-8') as f:
    code = f.read()

def repl_get(m):
    var = m.group(1)
    args = m.group(2)
    return f'_pos_get({var}, {args})'

def repl_sub(m):
    var = m.group(1)
    key = m.group(2)
    return f'_pos_get({var}, "{key}")'

new_code = re.sub(r'\b(p|pos)\.get\(([^)]+)\)', repl_get, code)
new_code = re.sub(r'\b(p|pos)\["([^"]+)"\]', repl_sub, new_code)
new_code = re.sub(r"\b(p|pos)\['([^']+)'\]", repl_sub, new_code)

with open('mock_ws_server.py', 'w', encoding='utf-8') as f:
    f.write(new_code)
print('Replaced usages of p.get, pos.get, p[], pos[]')
