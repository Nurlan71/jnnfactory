import os, re

d = r'D:\Info\JNN\Soft\Jnnfactory'
p = re.compile(r'<script[^>]*src="/assets/tilda-[^"]*"[^>]*></script>', re.I)
c = 0
for f in os.listdir(d):
    if f.endswith('.html'):
        fp = os.path.join(d, f)
        with open(fp, 'r', encoding='utf-8') as h:
            t = h.read()
        n = p.sub('', t)
        if n != t:
            with open(fp, 'w', encoding='utf-8') as h:
                h.write(n)
            c += 1
            print(f'Очищен: {f}')
print(f'\nВсего очищено: {c}')