const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

async function main() {
  const input = path.resolve(process.argv[2]);
  const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  const executablePath = fs.existsSync(systemChrome) ? systemChrome : chromium.executablePath();
  const browser = await chromium.launch({ headless: true, executablePath });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`file://${input}`);
    if (await page.$("#fragment-contract")) {
      await page.click("#zoomIn");
      await page.click("#fragment-contract");
      const contractTitle = await page.textContent("#detailTitle");
      if (!contractTitle?.includes("Template JSON")) {
        throw new Error(`unexpected delivery contract title: ${contractTitle}`);
      }
      await page.click("#canonical");
      const title = await page.textContent("#detailTitle");
      if (!title?.includes("Canonical Resolution")) throw new Error(`unexpected detail title: ${title}`);
    } else if (await page.$("#consumer-entry")) {
      await page.click("#plus");
      await page.click("#consumer-entry");
      const entryTitle = await page.textContent("#detailTitle");
      if (!entryTitle?.includes("Consumer Entry")) {
        throw new Error(`unexpected consumer entry title: ${entryTitle}`);
      }
      await page.click("#availability-gate");
      const gateTitle = await page.textContent("#detailTitle");
      if (!gateTitle?.includes("Availability + Coverage Gate")) {
        throw new Error(`unexpected availability title: ${gateTitle}`);
      }
    } else if (await page.$("#metaone-adapter")) {
      await page.click("#plus");
      await page.click("#metaone-adapter");
      const adapterTitle = await page.textContent("#detailTitle");
      if (!adapterTitle?.includes("Capability Adapter")) {
        throw new Error(`unexpected adapter title: ${adapterTitle}`);
      }
      await page.click("#availability-gate");
      const gateTitle = await page.textContent("#detailTitle");
      if (!gateTitle?.includes("Availability + Coverage Gate")) {
        throw new Error(`unexpected availability title: ${gateTitle}`);
      }
    } else {
      throw new Error("unsupported architecture HTML fixture");
    }
    if (errors.length) throw new Error(errors.join("\n"));
    console.log("HTML interaction smoke test passed");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
