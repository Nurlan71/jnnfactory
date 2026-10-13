const fs = require('fs');
const path = require('path');

const dir = process.argv[2] || 'D:\\\\Info\\\\JNN\\\\Soft\\\\Jnnfactory';
const files = fs.readdirSync(dir, { recursive: true }).filter(f => f.endsWith('.html'));

const schemaBlock = `<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "JNN Factory",
  "url": "https://jnnfactory.online",
  "logo": "/img/logo.png",
  "description": "Производитель очков и оборудования для производства"
}
</script>`;

let added = 0;
for (const file of files) {
    const filePath = path.join(dir, file);
    let content = fs.readFileSync(filePath, 'utf-8');
    
    // Check if Schema already exists
    if (content.includes('application/ld+json')) {
        //console.log('Already has Schema: ' + file);
        continue;
    }
    
    // Add Schema.org Organization before closing </head>
    const newContent = content.replace('</head>', schemaBlock + '</head>');
    
    if (newContent !== content) {
        fs.writeFileSync(filePath, newContent);
        added++;
        console.log('Added Schema to: ' + file);
    }
}
console.log('Total files updated with Schema: ' + added);