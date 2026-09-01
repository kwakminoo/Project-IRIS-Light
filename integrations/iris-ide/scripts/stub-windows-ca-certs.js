/** Stub optional native @vscode/windows-ca-certs when node-gyp fails (localhost-only IRIS IDE). */
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', 'node_modules', '@vscode', 'windows-ca-certs');
const release = path.join(dir, 'build', 'Release');
try {
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(release, { recursive: true });
    fs.writeFileSync(
        path.join(dir, 'package.json'),
        JSON.stringify({ name: '@vscode/windows-ca-certs', version: '0.0.0-stub', main: 'index.js' }, null, 2),
        'utf8'
    );
    fs.writeFileSync(
        path.join(dir, 'index.js'),
        "'use strict';\nmodule.exports = { load: async () => undefined, getWindowsCaCerts: async () => [] };\n",
        'utf8'
    );
    // ponytail: esbuild only needs the path to exist for bundle — runtime uses stub JS
    fs.writeFileSync(path.join(release, 'crypt32.node'), Buffer.alloc(0));
    console.log('[iris-ide] stubbed @vscode/windows-ca-certs');
} catch (err) {
    console.warn('[iris-ide] windows-ca-certs stub skipped:', err.message);
}
