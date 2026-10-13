# Setup Tailwind CSS for jnnfactory site
Write-Host "=== Setting up Tailwind CSS ==="

# 1. Initialize npm project (if not already)
if (-not (Test-Path 'package.json')) {
    npm init -y | Out-Null
}

# 2. Install dependencies
Write-Host "Installing Tailwind dependencies..."
npm install tailwindcss postcss autoprefixer | Out-Null

# 3. Initialize Tailwind
Write-Host "Initializing Tailwind..."
npx tailwindcss init -p | Out-Null

# 4. Create tailwind.config.js
Write-Host "Creating tailwind.config.js..."
Set-Content -Path 'tailwind.config.js' -Value @'
module.exports = {
  content: [
    "**.html",
    "**.php",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
'@

# 5. Create assets/css directory and src.css
Write-Host "Creating assets/css directory..."
New-Item -ItemType Directory -Path 'assets/css' -Force | Out-Null

Write-Host "Creating assets/css/src.css..."
Set-Content -Path 'assets/css/src.css' -Value @'
@tailwind base;
@tailwind components;
@tailwind utilities;
'@

# 6. Replace Tilda CSS links in all HTML files
Write-Host "Replacing Tilda CSS links with src.css..."
Get-ChildItem -Filter '*.html' -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName
    # Replace any Tilda min.css references
    $newContent = $content -replace 'href="assets/tilda[^"]*\.min\.css"', 'href="/css/src.css"'
    if ($newContent -ne $content) {
        Set-Content -Path $_.FullName -Value $newContent
    }
}

# 7. Create .gitignore
Write-Host "Creating .gitignore..."
Set-Content -Path '.gitignore' -Value @'
# Dependencies
node_modules/
package-lock.json

# Build outputs
dist/
*.min.css
*.min.js

# Tilda assets (they are no longer needed in git, as we use our own CSS)
assets/tildaws/

# Logs
*.log

# Environment variables
.env

# Ignore admin folder (for now, we will delete later)
admin/
'

Write-Host "=== Tailwind setup complete ==="
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Run: git add -A && git commit -m ""feat: init Tailwind CSS, replace Tilda CSS links, add .gitignore"""
Write-Host "2. Run SEO/Schema.org setup"
Write-Host "3. Run admin removal and Vite setup"