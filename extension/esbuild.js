// @ts-check
const esbuild = require('esbuild');

const watch = process.argv.includes('--watch');
const production = process.argv.includes('--production');

/** @type {import('esbuild').BuildOptions} */
const options = {
    entryPoints: ['webview/main.ts'],
    bundle: true,
    format: 'iife',
    platform: 'browser',
    target: 'es2020',
    outfile: 'media/graph.js',
    sourcemap: !production,
    minify: production,
    logLevel: 'info',
};

async function run() {
    if (watch) {
        const ctx = await esbuild.context(options);
        await ctx.watch();
        console.log('[esbuild] watching webview...');
    } else {
        await esbuild.build(options);
        console.log('[esbuild] webview bundle written to media/graph.js');
    }
}

run().catch((e) => {
    console.error(e);
    process.exit(1);
});
