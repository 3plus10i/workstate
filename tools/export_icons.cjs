// Development-only SVG export. Pass a Sharp module path if it is not installed locally.
const sharp = require(process.argv[2] || 'sharp');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256];

async function exportIcon(source, pngName, icoName) {
  const svg = await fs.readFile(path.join(root, 'public', source));
  await sharp(svg, { density: 288 }).resize(512, 512).png().toFile(path.join(root, 'public', pngName));
  const images = await Promise.all(sizes.map(size => sharp(svg, { density: 288 }).resize(size, size).png().toBuffer()));
  const header = Buffer.alloc(6 + 16 * sizes.length);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(sizes.length, 4);
  let offset = header.length;
  images.forEach((image, index) => {
    const position = 6 + 16 * index;
    header[position] = sizes[index] % 256;
    header[position + 1] = sizes[index] % 256;
    header.writeUInt16LE(1, position + 4);
    header.writeUInt16LE(32, position + 6);
    header.writeUInt32LE(image.length, position + 8);
    header.writeUInt32LE(offset, position + 12);
    offset += image.length;
  });
  const ico = Buffer.concat([header, ...images]);
  await fs.writeFile(path.join(root, 'public', icoName), ico);
  return { ico, favicon: images[sizes.indexOf(32)] };
}

(async () => {
  const active = await exportIcon('workstate.svg', 'workstate.png', 'workstate.ico');
  await exportIcon('workstate-idle.svg', 'workstate-idle.png', 'icon_idle.ico');
  await fs.writeFile(path.join(root, 'public', 'icon_active.ico'), active.ico);
  await fs.writeFile(path.join(root, 'frontend', 'public', 'icon_active.ico'), active.ico);
  const htmlPath = path.join(root, 'frontend', 'index.html');
  const html = await fs.readFile(htmlPath, 'utf8');
  await fs.writeFile(htmlPath, html.replace(/<link rel="icon"[^>]*>/, `<link rel="icon" href="data:image/png;base64,${active.favicon.toString('base64')}" type="image/png">`));
})().catch(error => { console.error(error); process.exitCode = 1; });
