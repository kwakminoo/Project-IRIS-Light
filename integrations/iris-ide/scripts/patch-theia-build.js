#!/usr/bin/env node
/** ponytail: Theia collector skips root theiaExtensions — patch index + rebundle. */
'use strict';

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const indexPath = path.join(root, 'src-gen', 'frontend', 'index.js');
const iconPng = path.join(root, '..', '..', 'iris', 'assets', 'iris_icon.png');
const iconIco = path.join(root, '..', '..', 'iris', 'assets', 'iris_icon.ico');
const frontendDir = path.join(root, 'lib', 'frontend');

function copyIcon(name, src) {
    if (!fs.existsSync(src)) return;
    fs.copyFileSync(src, path.join(frontendDir, name));
}

function patchIndexHtml(filePath) {
    if (!fs.existsSync(filePath)) return false;
    let html = fs.readFileSync(filePath, 'utf8');
    let changed = false;

    if (html.includes('iris-ide-theme.css')) {
        html = html.replace(/\s*<link rel="stylesheet" href="\.\/iris-ide-theme\.css">\n?/g, '');
        changed = true;
    }
    if (html.includes('iris-ide-critical')) {
        html = html.replace(/\s*<style id="iris-ide-critical">[^<]*<\/style>\n?/g, '');
        changed = true;
    }
    if (html.includes("localStorage.setItem('theme-id','dark')")) {
        html = html.replace(/\s*<script>try\{localStorage\.setItem\('theme-id','dark'\)\}catch\(e\)\{\}<\/script>\n?/g, '');
        changed = true;
    }
    if (html.includes('iris-ide-theme')) {
        html = html.replace(
            /<body class="vs-dark iris-ide-theme theia-scope">/,
            '<body>'
        );
        html = html.replace(
            /<body class="theia-scope vs-dark iris-ide-theme">/,
            '<body>'
        );
        changed = true;
    }
    if (!html.includes('<title>IRIS IDE</title>') && html.includes('<title>')) {
        html = html.replace(/<title>[^<]*<\/title>/, '<title>IRIS IDE</title>');
        changed = true;
    }

    if (changed) {
        fs.writeFileSync(filePath, html);
    }
    return changed;
}

let rebundle = false;

if (!fs.existsSync(indexPath)) {
    console.warn('patch-theia-build: index.js missing — run theia build first');
} else {
    let src = fs.readFileSync(indexPath, 'utf8');
    let changed = false;

    if (!src.includes('iris-ide-frontend-module')) {
        const needle = 'MonacoInit.init(container);';
        const insert =
            "await load(container, import('../../lib/browser/iris-ide-frontend-module'));\n        " +
            needle;
        if (src.includes(needle)) {
            src = src.replace(needle, insert);
            changed = true;
            console.log('patch-theia-build: injected iris-ide-frontend-module');
        }
    }

    if (src.includes('"applicationName": "Eclipse Theia"')) {
        src = src.replace(/"applicationName":\s*"Eclipse Theia"/g, '"applicationName": "IRIS IDE"');
        changed = true;
    }

    if (changed) {
        fs.writeFileSync(indexPath, src);
        rebundle = true;
    }
}

for (const htmlPath of [
    path.join(frontendDir, 'index.html'),
    path.join(root, 'src-gen', 'frontend', 'index.html'),
]) {
    if (patchIndexHtml(htmlPath)) {
        console.log('patch-theia-build: cleaned', path.relative(root, htmlPath));
    }
}

copyIcon('favicon.png', iconPng);
copyIcon('iris_icon.png', iconPng);
if (fs.existsSync(iconIco)) {
    copyIcon('favicon.ico', iconIco);
}

function copyPdfJs() {
    const srcDir = path.join(root, 'vendor', 'pdfjs');
    const destDir = path.join(frontendDir, 'pdfjs');
    if (!fs.existsSync(path.join(srcDir, 'pdf.mjs')) || !fs.existsSync(path.join(srcDir, 'pdf.worker.mjs'))) {
        console.warn('patch-theia-build: vendor/pdfjs missing — Iris PDF viewer assets not copied');
        return false;
    }
    fs.mkdirSync(destDir, { recursive: true });
    for (const name of ['pdf.mjs', 'pdf.worker.mjs']) {
        fs.copyFileSync(path.join(srcDir, name), path.join(destDir, name));
    }
    console.log('patch-theia-build: copied vendor/pdfjs → lib/frontend/pdfjs');
    return true;
}
copyPdfJs();

const bundlePath = path.join(frontendDir, 'bundle.js');
const bundleText = fs.existsSync(bundlePath) ? fs.readFileSync(bundlePath, 'utf8') : '';
const bundleHasIris = bundleText.includes('iris-ide-frontend-module');
// ponytail: module 문자열만 보면 스킵되어 구번들이 남는다.
// 시작 화면(showStartScreen)과 셸 맞춤 실행(IRIS_EXIT:)이 없으면 다시 묶는다.
const bundleHasCurrentExt =
    bundleText.includes('iris.ide.openFolder') &&
    bundleText.includes('ide.pick_open_folder') &&
    bundleText.includes('iris.ide.showStartScreen') &&
    bundleText.includes('iris.ide.runFile') &&
    bundleText.includes('IRIS_EXIT:') &&
    bundleText.includes('setDiagnostics') &&
    bundleText.includes('iris.pdf') &&
    bundleText.includes('iris-pdf');
if (rebundle || !bundleHasIris || !bundleHasCurrentExt) {
    console.log('patch-theia-build: rebundling frontend (iris extension)...');
    execSync('node esbuild.mjs', { cwd: root, stdio: 'inherit' });
    patchIndexHtml(path.join(frontendDir, 'index.html'));
}

console.log('patch-theia-build: ok');
