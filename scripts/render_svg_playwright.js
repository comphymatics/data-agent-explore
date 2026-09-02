const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

async function main() {
  const input = path.resolve(process.argv[2]);
  const output = path.resolve(process.argv[3] || input.replace(/\.svg$/, ".png"));
  const source = fs.readFileSync(input, "utf8");
  const width = Number((source.match(/width="(\d+)/) || [])[1] || 1800);
  const height = Number((source.match(/height="(\d+)/) || [])[1] || 1450);
  const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  const executablePath = fs.existsSync(systemChrome) ? systemChrome : chromium.executablePath();
  const browser = await chromium.launch({ headless: true, executablePath });
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 2 });
    const encoded = Buffer.from(source).toString("base64");
    await page.setContent(`<html><body style="margin:0;background:white"><img style="display:block" width="${width}" height="${height}" src="data:image/svg+xml;base64,${encoded}"></body></html>`);
    await page.screenshot({ path: output, type: "png" });
    console.log(`${output} (${width * 2}x${height * 2})`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
