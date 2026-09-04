import os
import glob

public_dir = '/Users/nathanlukewijaya/Documents/YCWC - Homework Helper/public'
html_files = glob.glob(os.path.join(public_dir, '*.html'))

for file in html_files:
    with open(file, 'r') as f:
        content = f.read()
    content = content.replace('/public/css/', '/css/')
    content = content.replace('/public/js/', '/js/')
    with open(file, 'w') as f:
        f.write(content)
print("HTML files updated.")
