'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const React = require('react');
const ts = require('typescript');

const build = require('../package.json').scripts.build;
assert.match(build, /^tsc &&/, 'IDE build must compile local extension sources before bundling');
assert.match(fs.readFileSync(path.join(__dirname, 'patch-theia-build.js'), 'utf8'),
    /bundleText\.includes\('iris-markdown-preview-breadcrumb'\)/,
    'installed runtime must rebundle when its preview action is missing');

const source = ts.createSourceFile('iris-markdown-breadcrumbs.tsx', fs.readFileSync(path.join(
    __dirname, '../src/browser/iris-markdown-breadcrumbs.tsx'), 'utf8'),
    ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const declaration = source.statements.find(node => ts.isClassDeclaration(node));
assert.ok(declaration, 'Markdown breadcrumbs renderer must exist');
const method = declaration.members.find(node => node.name?.getText(source) === 'renderBreadcrumbs');
assert.ok(method, 'Markdown breadcrumbs renderer must render the preview action');
const compiled = ts.transpileModule(`class Renderer extends Base { ${method.getText(source)} }; Renderer`, {
    compilerOptions: { target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React },
}).outputText;
const Renderer = vm.runInNewContext(compiled, {
    React,
    Base: class { renderBreadcrumbs() { return this.breadcrumbs.map(crumb => this.breadcrumbRenderer.render(crumb)); } },
});

for (const name of ['test.md', 'README.MARKDOWN', 'notes.mdown']) {
    const renderer = new Renderer();
    renderer.uri = { path: { toString: () => `/project/${name}` } };
    renderer.breadcrumbs = [{ containerClass: 'file', label: name }, { label: 'Heading' }];
    renderer.breadcrumbRenderer = { render: crumb => React.createElement('li', null, crumb.label) };
    const calls = [];
    renderer.commandRegistry = { executeCommand: (...args) => calls.push(args) };
    const rendered = renderer.renderBreadcrumbs();
    const elements = React.Children.toArray(rendered.props?.children || rendered);
    const button = elements.flatMap(element => React.Children.toArray(element.props.children))
        .find(element => element.type === 'button');
    assert.ok(button, `${name} should show preview`);
    assert.equal(elements[0].props.children, name);
    assert.equal(elements[1].props.className, 'iris-markdown-preview-breadcrumb');
    assert.equal(elements[2].props.children, 'Heading');
    assert.equal(button.props.children, '프리뷰');
    button.props.onClick();
    assert.deepEqual(calls, [['markdown.showPreview']]);
}

for (const name of ['test.py', 'diagram.svg', 'notes.mdx', 'test.md.bak']) {
    const renderer = new Renderer();
    renderer.uri = { path: { toString: () => `/project/${name}` } };
    renderer.breadcrumbs = [{ containerClass: 'file', label: name }];
    renderer.breadcrumbRenderer = { render: crumb => React.createElement('li', null, crumb.label) };
    const rendered = renderer.renderBreadcrumbs();
    assert.equal(React.Children.toArray(rendered.props?.children || rendered)
        .some(element => React.Children.toArray(element.props.children)
            .some(child => child.type === 'button')), false, `${name} should not show preview`);
}

console.log('markdown preview breadcrumbs check ok');
