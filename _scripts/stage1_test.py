import os, re

site_dir = r'D:\Info\JNN\Soft\Jnnfactory'

# Test on ONE file first: index.html
test_file = os.path.join(site_dir, 'index.html')
with open(test_file, 'r', encoding='utf-8') as f:
    content = f.read()

original = content

# 1. Replace old favicon references with our local one
content = re.sub(r'<link[^>]*rel=["\']shortcut icon["\'][^>]*>',
                  '<link rel="shortcut icon" href="/assets/favicon-tshirt.png" type="image/png">', content, flags=re.I)

# Also replace any tildafavicon.ico or tildacdn favicon references specifically
content = re.sub(r'href="[^"]*tildafavicon[^"]*"', 'href="/assets/favicon-tshirt.png"', content, flags=re.I)

# 2. Remove only external DNS-prefetch to tildacdn.com and static.tildacdn.ink
content = re.sub(r'<link[^>]*href="https?://[^"]*tildacdn[^"]*"[^>]*>\s*', '', content)
content = re.sub(r'<link[^>]*href="https?://[^"]*static\.tildacdn[^"]*"[^>]*>\s*', '', content)

# 3. Remove hidden Tilda labels (style blocks)
content = re.sub(r'<style>\s*\.tildalabel[^<]*</style>', '', content, flags=re.I)

changes = original != content
print(f'Test file: index.html -> changes detected: {changes}')
print(f'Original length: {len(original)}, New length: {len(content)}')

# Save test
with open(test_file, 'r', encoding='utf-8') as f:
    before = f.read()

# Only save if changes were made
if changes:
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Saved index.html')
else:
    print('No changes to save')