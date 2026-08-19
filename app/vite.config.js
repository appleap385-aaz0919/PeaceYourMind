import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages는 https://<user>.github.io/PeaceYourMind/ 하위에 서빙한다.
// base를 맞추지 않으면 자산 경로가 루트로 잡혀 전부 404가 난다.
const BASE = "/PeaceYourMind/";

export default defineConfig({
  base: BASE,
  plugins: [react()],
  define: {
    // 영상 데이터는 앱과 같은 오리진의 data/ 하위에 배치가 따로 배포한다
    // (build.yml이 destination_dir: data, keep_files: true로 올린다).
    // 구절(verses.json)은 여기 없다 — 앱 번들에 들어간다. 매일 바뀌는 값이
    // 아니고, 네트워크가 없어도 구절 화면은 떠야 하기 때문이다.
    __DATA_BASE__: JSON.stringify(`${BASE}data/`),
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 700,
  },
});
