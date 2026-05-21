const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const required = [
  ['Embedded Python', path.join(root, 'runtime', 'python', 'python.exe')],
  ['PostgreSQL server', path.join(root, 'runtime', 'postgresql', 'bin', 'postgres.exe')],
  ['PostgreSQL initdb', path.join(root, 'runtime', 'postgresql', 'bin', 'initdb.exe')],
  ['PostgreSQL createdb', path.join(root, 'runtime', 'postgresql', 'bin', 'createdb.exe')]
];

const missing = required.filter(([, file]) => !fs.existsSync(file));
if (missing.length) {
  console.error('Missing embedded Windows runtime files:');
  for (const [label, file] of missing) {
    console.error(`- ${label}: ${file}`);
  }
  console.error('\nPopulate windows/runtime before packaging. See windows/runtime/README.md.');
  process.exit(1);
}

console.log('Embedded runtime check passed.');

