import re
with open('app/models.py', 'r') as f:
    content = f.read()
back_pops = re.findall(r'back_populates="([^"]+)"', content)
from collections import Counter
cnt = Counter(back_pops)
for k, v in cnt.most_common():
    print(f'{v}: {k}')