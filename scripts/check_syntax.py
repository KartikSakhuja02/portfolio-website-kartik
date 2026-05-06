import ast
import sys
p='backend/app/services/github.py'
try:
    s=open(p,'r',encoding='utf-8').read()
    ast.parse(s)
    print('ok')
except Exception as e:
    print(type(e).__name__+':',e)
    sys.exit(1)
