import os, shutil, datetime

site_dir = r'D:\Info\JNN\Soft\Jnnfactory'
backup_dir = os.path.join(site_dir, '_backup_html_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))

os.makedirs(backup_dir, exist_ok=True)
count = 0
for f in os.listdir(site_dir):
    if f.endswith('.html'):
        shutil.copy2(os.path.join(site_dir, f), os.path.join(backup_dir, f))
        count += 1

print(f'Backup created: {count} HTML files -> {backup_dir}')