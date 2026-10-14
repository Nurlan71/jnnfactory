import os, re

site_dir = r'D:\Info\JNN\Soft\Jnnfactory'
count = 0

for fname in os.listdir(site_dir):
    if not fname.endswith('.html'):
        continue
    fpath = os.path.join(site_dir, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # 1. Replace old favicon references
    content = re.sub(r'href="[^"]*tildafavicon[^"]*"',
                      'href="/assets/favicon-tshirt.png"', content, flags=re.I)
    content = re.sub(r'<link[^>]*rel=["\']shortcut icon["\'][^>]*href="[^"]*"[^>]*>',
                      '<link rel="shortcut icon" href="/assets/favicon-tshirt.png" type="image/png">', content, flags=re.I)
    # If no favicon link exists, add one before </head>
    if 'favicon-tshirt.png' not in content and '</head>' in content:
        content = content.replace('</head>',
            '<link rel="shortcut icon" href="/assets/favicon-tshirt.png" type="image/png">\n</head>')
    
    # 2. Remove external DNS-prefetch to tildacdn.com
    content = re.sub(r'<link[^>]*href="https?://[^"]*tildacdn[^"]*"[^>]*>\s*', '', content)
    
    # 3. Remove hidden Tilda labels
    content = re.sub(r'<style>\s*\.tildalabel[^<]*</style>', '', content, flags=re.I)
    
    if original != content:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        count += 1

print(f'Обработано файлов: {count}')