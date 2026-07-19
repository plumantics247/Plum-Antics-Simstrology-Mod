const fs = require("fs");
const path = require("path");
const { DdsImage } = require("@s4tk/images");

const ROOT = path.resolve(__dirname, "..");
const RAW_DIR = path.join(ROOT, "src", "OuterPlanets", "DstSource");
const DST_DIR = path.join(ROOT, "src", "OuterPlanets", "DstImage");

const ICONS = [
  {
    source: "Uranus.DXT5 40x40.DSTImage",
    target: "00B2D882_00000000_A8F7344C2D7B91E1.dds",
  },
  {
    source: "Neptune.DXT5 40x40.DSTImage",
    target: "00B2D882_00000000_B61C9D4F7AE20358.dds",
  },
  {
    source: "Chiron_Pluto.DXT5 40x40.DSTImage",
    target: "00B2D882_00000000_C4E8A91B5FD07236.dds",
  },
];

async function main() {
  fs.mkdirSync(DST_DIR, { recursive: true });

  for (const icon of ICONS) {
    const sourcePath = path.join(RAW_DIR, icon.source);
    const targetPath = path.join(DST_DIR, icon.target);
    const sourceBuffer = fs.readFileSync(sourcePath);
    const dds = await DdsImage.fromImageAsync(sourceBuffer, {
      shuffle: true,
      maxMipMaps: 1,
    });
    fs.writeFileSync(targetPath, dds.buffer);
    console.log(`wrote ${path.relative(ROOT, targetPath)}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
