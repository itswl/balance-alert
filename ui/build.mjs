// 构建脚本：esbuild 打包 + index.html 注入构建标识。
//
// 产物固定叫 app.js / app.css，路径写死在 index.html 里，Go 那边直接
// `//go:embed all:dist` 再把 dist/static 挂到 /static 即可，不需要读清单文件。
// 缓存失效靠 ?v=<内容哈希> 的查询串，文件名保持稳定。

import { createHash } from 'node:crypto';
import { mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, context } from 'esbuild';

const root = dirname(fileURLToPath(import.meta.url));
const outdir = resolve(root, 'dist');
const staticDir = join(outdir, 'static');
const testOutdir = resolve(root, 'dist-test');

const watch = process.argv.includes('--watch');
const testOnly = process.argv.includes('--test');

/** @type {import('esbuild').BuildOptions} */
const shared = {
  bundle: true,
  format: 'iife',
  target: ['es2022', 'chrome109', 'firefox115', 'safari16'],
  charset: 'utf8',
  logLevel: 'info',
  absWorkingDir: root,
};

/** 把 __BUILD_ID__ 换成产物内容的哈希；产物没变时哈希也不变，浏览器缓存继续有效 */
async function emitHtml() {
  const [js, css] = await Promise.all([
    readFile(join(staticDir, 'app.js')),
    readFile(join(staticDir, 'app.css')),
  ]);
  const buildId = createHash('sha256').update(js).update(css).digest('hex').slice(0, 12);
  const html = await readFile(join(root, 'index.html'), 'utf8');
  await writeFile(join(outdir, 'index.html'), html.replaceAll('__BUILD_ID__', buildId), 'utf8');
  return buildId;
}

async function reportSizes(buildId) {
  const files = ['index.html', 'static/app.js', 'static/app.css'];
  const { gzipSync, brotliCompressSync } = await import('node:zlib');
  console.log(`\n构建标识 ${buildId}`);
  for (const file of files) {
    const buf = await readFile(join(outdir, file));
    const gz = gzipSync(buf, { level: 9 }).length;
    const br = brotliCompressSync(buf).length;
    console.log(
      `  ${file.padEnd(16)} ${String(buf.length).padStart(7)} B  gzip ${String(gz).padStart(6)} B  br ${String(br).padStart(6)} B`,
    );
  }
}

async function buildApp() {
  await rm(outdir, { recursive: true, force: true });
  await mkdir(staticDir, { recursive: true });

  await build({
    ...shared,
    entryPoints: [
      { in: resolve(root, 'src/main.ts'), out: 'app' },
      { in: resolve(root, 'src/styles/index.css'), out: 'app' },
    ],
    outdir: staticDir,
    minify: true,
    sourcemap: false,
  });

  const buildId = await emitHtml();
  await reportSizes(buildId);
}

async function watchApp() {
  await mkdir(staticDir, { recursive: true });
  const ctx = await context({
    ...shared,
    entryPoints: [
      { in: resolve(root, 'src/main.ts'), out: 'app' },
      { in: resolve(root, 'src/styles/index.css'), out: 'app' },
    ],
    outdir: staticDir,
    minify: false,
    sourcemap: 'inline',
    plugins: [
      {
        name: 'emit-html',
        setup(b) {
          b.onEnd(async (result) => {
            if (result.errors.length === 0) {
              const id = await emitHtml();
              console.log(`index.html 已更新（${id}）`);
            }
          });
        },
      },
    ],
  });
  await ctx.watch();
  console.log('watching…');
}

/** 测试：把 test/*.test.ts 各自打成一个 ESM 文件，交给 node --test 跑 */
async function buildTests() {
  await rm(testOutdir, { recursive: true, force: true });
  await mkdir(testOutdir, { recursive: true });

  const entries = (await readdir(resolve(root, 'test')))
    .filter((f) => f.endsWith('.test.ts'))
    .map((f) => resolve(root, 'test', f));
  if (entries.length === 0) throw new Error('test/ 下没有 *.test.ts');

  await build({
    ...shared,
    entryPoints: entries,
    outdir: testOutdir,
    outExtension: { '.js': '.mjs' },
    format: 'esm',
    platform: 'node',
    minify: false,
    sourcemap: 'inline',
    // node:test 由运行时提供，不打进包里
    external: ['node:*'],
  });

  const built = await readdir(testOutdir);
  console.log(`已构建 ${built.length} 个测试文件`);
}

if (testOnly) {
  await buildTests();
} else if (watch) {
  await watchApp();
} else {
  await buildApp();
  // 让 Go 那边一眼看出 embed 要包哪些文件
  const listing = await readdir(outdir, { recursive: true });
  const files = [];
  for (const entry of listing) {
    const full = join(outdir, entry);
    if ((await stat(full)).isFile()) files.push(entry);
  }
  console.log(`\ndist/ 共 ${files.length} 个文件：${files.sort().join(', ')}`);
}
