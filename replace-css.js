const fs = require('fs');
const path = require('path');

const dir = process.argv[2] || 'D:\\Info\\JNN\\Soft\\Jnnfactory';
const files = fs.readdirSync(dir, { recursive: true }).filter(f => f.endsWith('.html'));

let replaced = 0;
const regex = /href="[^"]*tilda[^"]*\.min.css"/gi;
for (const file of files) {
    const filePath = path.join(dir, file);
    let content = fs.readFileSync(filePath, 'utf-8');
    const newContent = content.replace(regex, 'href="/css/src.css"');
    if (newContent !== content) {
        fs.writeFileSync(filePath, newContent);
        replaced++;
        console.log('Replaced: ' + file);
    }
}
console.log('Total files replaced: ' + replaced);