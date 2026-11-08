import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { setTimeout as delay } from "node:timers/promises";

// Exercise the production server, including rewrites and response headers.
const reservation = createServer();
await new Promise((resolve) => reservation.listen(0, "127.0.0.1", resolve));
const port = reservation.address().port;
await new Promise((resolve) => reservation.close(resolve));
const base = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", String(port)], {
  stdio: ["ignore", "pipe", "pipe"],
});
let logs = "";
server.stdout.on("data", (data) => { logs += data; });
server.stderr.on("data", (data) => { logs += data; });
const stopped = new Promise((resolve) => server.once("exit", resolve));

async function read(path, type) {
  const response = await fetch(`${base}${path}`, { signal: AbortSignal.timeout(10000) });
  assert.equal(response.status, 200, path);
  assert.ok(response.headers.get("content-type")?.includes(type), `${path}: content type`);
  return response.text();
}

try {
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(logs);
    try {
      await read("/", "text/html");
      ready = true;
      break;
    } catch {
      await delay(100);
    }
  }
  assert.ok(ready, `Server did not start: ${logs}`);
  const home = await read("/", "text/html");
  assert.match(home, /<link rel="canonical" href="https:\/\/ipa-forge\.nandan\.fyi"/);
  assert.match(home, /application\/ld\+json/);
  const robots = await read("/robots.txt", "text/plain");
  assert.match(robots, /Sitemap: https:\/\/ipa-forge\.nandan\.fyi\/sitemap.xml/);
  const sitemap = await read("/sitemap.xml", "application/xml");
  const index = await read("/llms.txt", "text/plain");
  assert.match(index, /Package version:/);
  assert.match(index, /IPA_FORGE_PATCHES_DIR/);
  const links = [...index.matchAll(/\]\((https:\/\/ipa-forge\.nandan\.fyi\/docs[^)]*\.md)\)/g)];
  assert.ok(links.length > 0, "No absolute Markdown links in agent index");
  for (const [, url] of links) {
    const path = new URL(url).pathname;
    const markdown = await read(path, "text/markdown");
    assert.match(markdown, /^# .+\n\nSource: https:\/\/ipa-forge\.nandan\.fyi\/docs/);
    assert.match(markdown, /Package version:/);
    const canonical = path.slice(0, -3);
    assert.ok(sitemap.includes(canonical), `${canonical} absent from sitemap`);
    const html = await read(canonical, "text/html");
    assert.ok(html.includes(`rel="canonical" href="https://ipa-forge.nandan.fyi${canonical}"`), `${canonical}: canonical`);
  }
  const schema = JSON.parse(await read("/schema/patch-definition.json", "application/json"));
  assert.equal(schema.title, "PatchDefinition");
  assert.ok(schema.properties.patches.items.discriminator.mapping.binary_replace);
  const full = await read("/llms-full.txt", "text/plain");
  assert.ok(full.includes("Source: https://ipa-forge.nandan.fyi/docs"));
  const missing = await fetch(`${base}/docs/this-page-does-not-exist.md`);
  assert.equal(missing.status, 404);
  console.log(`Docs smoke check passed: homepage, robots, sitemap, ${links.length} HTML/Markdown pairs, agent index and full text.`);
} finally {
  server.kill("SIGTERM");
  await stopped;
}
