import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const tshirt = process.argv.includes("--tshirt");
const out = path.resolve(
  tshirt
    ? "../work/samples/2026-11-10-tshirt-bag"
    : "../work/samples/2026-11-10-remotion",
);
const compositionId = tshirt ? "TshirtBag" : "DrawerWax";
const outputName = tshirt
  ? "life-tip-tshirt-bag.mp4"
  : "life-tip-drawer-remotion.mp4";
const started = Date.now();
const serveUrl = await bundle({
  entryPoint: path.resolve("src/index.ts"),
  outDir: path.join(out, "bundle"),
  rspack: true,
});
const composition = await selectComposition({ serveUrl, id: compositionId });
let last = -1;
const overrides = [];
await renderMedia({
  serveUrl,
  composition,
  codec: "h264",
  crf: 18,
  x264Preset: "fast",
  concurrency: 1,
  outputLocation: path.join(out, outputName),
  overwrite: true,
  ffmpegOverride: ({ type, args }) => {
    const bounded = [
      "-threads",
      "1",
      "-filter_threads",
      "1",
      ...args.slice(0, -1),
      "-threads",
      "1",
      args[args.length - 1],
    ];
    overrides.push({ type, args: bounded });
    return bounded;
  },
  onProgress: ({ progress }) => {
    const step = Math.floor(progress * 10);
    if (step !== last) {
      last = step;
      console.log(`Render ${step * 10}%`);
    }
  },
});
const metadata = JSON.parse(
  await readFile(path.join(out, "metadata.json"), "utf8"),
);
await writeFile(
  path.join(out, "render-receipt.json"),
  JSON.stringify(
    {
      renderer: "Remotion 4.0.542",
      composition: composition.id,
      width: composition.width,
      height: composition.height,
      fps: composition.fps,
      frames: composition.durationInFrames,
      renderSeconds: (Date.now() - started) / 1000,
      ffmpegThreads: 1,
      narration: metadata.spokenScript,
      uploaded: false,
      ffmpegCalls: overrides,
    },
    null,
    2,
  ),
);
console.log("Local MP4 complete; no uploader invoked.");
