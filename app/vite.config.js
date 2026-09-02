import { readFileSync, rmSync, existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 앱 버전 — package.json이 단일 소스다. "이 앱에 대해" 화면이 표시한다.
// 스토어 심사·사용자 문의에서 "어느 빌드를 보고 있는가"를 물으므로 화면에
// 떠 있어야 하고, 손으로 적으면 반드시 실제 버전과 어긋난다.
// ⚠ 안드로이드 versionCode/versionName도 같은 값에서 나온다
//   (android/app/build.gradle이 이 package.json을 직접 읽는다).
const { version } = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf8"),
);

// GitHub Pages는 https://<user>.github.io/PeaceYourMind/ 하위에 서빙한다.
// base를 맞추지 않으면 자산 경로가 루트로 잡혀 전부 404가 난다.
const BASE = "/PeaceYourMind/";

// 배포된 웹의 주소. 앱은 번들로 돌지만 **영상 데이터만은** 여기서 받는다.
const SITE = `https://appleap385-aaz0919.github.io${BASE}`;

/**
 * [왜 빌드가 둘인가 — 2026-08-31]
 *   웹(gh-pages)과 앱(Capacitor)은 **서빙 오리진이 다르다.**
 *     웹  https://appleap385-aaz0919.github.io/PeaceYourMind/
 *     앱  https://localhost/            (Capacitor가 APK 자산을 여기 띄운다)
 *   그래서 base·데이터 경로·서비스워커·광고가 전부 갈린다.
 *
 *   ⛔ 앱 빌드는 **dist가 아니라 dist-app에 쓴다.** deploy-app.yml이
 *     `publish_dir: ./app/dist`를 웹에 올리기 때문이다 — 같은 자리에 쓰면
 *     앱 번들이 웹으로 배포될 수 있다. 디렉터리를 가르는 것이 유일한 방어다.
 */
export default defineConfig(({ mode }) => {
  const IS_APP = mode === "capacitor";

  return {
    base: IS_APP ? "./" : BASE,
    plugins: [react(), IS_APP ? appBuildGuards() : null].filter(Boolean),
    define: {
      // 영상 데이터는 배치가 하루 2회 갱신한다. 앱도 번들이 아니라 이걸 받는다.
      //   웹  같은 오리진의 data/ (build.yml이 destination_dir: data로 올린다)
      //   앱  ⚠ **절대 URL이다.** 번들에는 seed-videos.json만 있고 최신 목록은
      //      원격이라, 오리진이 localhost인 앱에서는 상대 경로가 성립하지 않는다.
      //      GitHub Pages가 Access-Control-Allow-Origin: * 를 준다(실측 확인).
      __DATA_BASE__: JSON.stringify(IS_APP ? `${SITE}data/` : `${BASE}data/`),
      // 개역한글 장 본문("이어서 읽기"). data/ 하위가 **아니다** —
      // data/는 배치(build.yml)가 매일 덮어쓰는 영역이고, 원문은 바뀌지 않는
      // 자산이라 앱과 함께 배포된다(app/public/krv/ → gh-pages 루트).
      // ★ 앱에서는 **APK 안에 들어간다**(942KB). 그래서 오프라인 첫 실행에서도
      //   이어서 읽기가 열린다 — 웹에는 없는 성질이다.
      __KRV_BASE__: JSON.stringify(IS_APP ? "/krv/" : `${BASE}krv/`),
      __APP_VERSION__: JSON.stringify(version),
      // ⛔ 앱인가. 광고·서비스워커·방침 링크가 이 하나로 갈린다.
      //   기본값을 웹(false)으로 두어 **앱 쪽이 명시적으로 켜져야** 하게 했다.
      __IS_APP__: JSON.stringify(IS_APP),
      // AdMob 배너 단위 ID — ⛔ **저장소에는 값을 두지 않는다.**
      //   App ID와 **같은 파일**(android/admob.properties)에서 읽는다.
      //   ⚠ 환경변수였던 것을 여기로 옮겼다 (2026-09-02 · HANDOFF 2.102).
      //     잊으면 광고도 고지도 없는 앱이 나가는데 게이트가 전부 통과했다.
      __ADMOB_BANNER_ID__: JSON.stringify(IS_APP ? readAdmobBannerId() : ""),
    },
    build: {
      outDir: IS_APP ? "dist-app" : "dist",
      emptyOutDir: true,
      chunkSizeWarningLimit: 700,
    },
  };
});

/**
 * AdMob 배너 단위 ID를 `android/admob.properties`에서 읽는다.
 *
 * [⛔ 왜 환경변수를 걷어냈나 — 2026-09-02 (HANDOFF 2.102)]
 *   `ADMOB_BANNER_ID=...`를 빠뜨리고 릴리스를 말면 값이 빈 문자열이 되고,
 *   adsEnabled가 false가 되어 **광고도 고지도 없는 앱**이 나간다.
 *   그런데 게이트는 전부 통과한다 — 데모 검사는 "데모가 있는가"만 보고,
 *   회귀는 "소스에 값이 없는가"라는 **반대 방향**만 보기 때문이다.
 *   ★ 3절 「일하는 방식」 ⓪-2의 "실패가 성공처럼 보이는" 자리이고,
 *     데모가 남는 실패보다 신호가 더 없다 — 화면에 배너만 없을 뿐이다.
 *   → 잊을 자리를 없앤다. App ID와 한 파일에 두면 **둘이 함께 움직인다.**
 *     (데모로 되돌릴 때 하나만 바꿔 퍼블리셔가 갈리던 문제도 같이 닫힌다.)
 *
 * ⚠ 웹 빌드는 이 파일을 보지 않는다. 웹은 AdSense이고 AdMob 값을 갖지 않는다 —
 *   그래서 gh-pages CI에 이 파일이 없어도 웹 빌드는 선다.
 */
function readAdmobBannerId() {
  const file = new URL("./android/admob.properties", import.meta.url);
  if (!existsSync(file)) {
    throw new Error(
      "[pym] AdMob 값이 없습니다: app/android/admob.properties\n" +
        "  android/admob.properties.example 을 복사하고 값 둘을 채우세요.\n" +
        "  ⛔ 이 파일은 .gitignore 대상입니다. 저장소에 값을 두지 않습니다.",
    );
  }

  // .properties 최소 파서 — key=value 이고 # 와 ! 는 주석이다.
  const props = new Map();
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#") || t.startsWith("!")) continue;
    const eq = t.indexOf("=");
    if (eq > 0) props.set(t.slice(0, eq).trim(), t.slice(eq + 1).trim());
  }

  // ⛔ 빈 값으로 조용히 가지 않는다. **빌드를 세우는 것**이 이 함수의 요점이다.
  //   형식까지 보는 이유는 App ID와 단위를 서로 바꿔 넣는 실수가 잦기 때문이다.
  const id = props.get("admob.bannerId") || "";
  if (!/^ca-app-pub-\d+\/\d+$/.test(id)) {
    throw new Error(
      `[pym] admob.bannerId 형식이 틀렸습니다: '${id}'\n` +
        "  ca-app-pub-<숫자>/<숫자> 여야 합니다 (빗금 / 로 구분되는 광고 단위 ID).\n" +
        "  ⚠ 물결 ~ 로 구분되는 것은 단위가 아니라 App ID입니다 — admob.appId 쪽입니다.\n" +
        "  고칠 곳  app/android/admob.properties  의  admob.bannerId",
    );
  }
  return id;
}

/**
 * 앱 빌드에서 AdSense를 **물리적으로 들어내는** 플러그인.
 *
 * ⛔ 왜 코드 분기만으로는 부족한가 (사용자 결정 2026-08-31)
 *   지금은 `AD_SLOT`이 빈 문자열이라 광고가 그려지지 않는다. 그런데 웹 심사가
 *   통과해 그 값이 채워지는 날, **같은 소스가 앱에서도 광고를 켠다.**
 *   앱은 AdSense를 쓰지 않기로 했고(프로그램 정책이 앱 내 AdSense를 금지한다),
 *   그 약속을 "그때 잊지 않기"에 맡길 수 없다. 그래서 빌드가 지운다.
 *
 * ⚠ 지우는 것으로 끝내지 않고 **지웠는지 검사한다.** index.html이 바뀌어
 *   정규식이 빗나가면 조용히 통과하는 것이 가장 나쁜 결과이기 때문이다.
 */
function appBuildGuards() {
  const AD_HOST = "googlesyndication";

  return {
    name: "pym-app-build-guards",

    // ① index.html — base 경로 하드코딩을 걷고 AdSense 태그를 들어낸다.
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        // /PeaceYourMind/... 는 앱 오리진(https://localhost/)에서 전부 404다.
        let out = html.split(BASE).join("./");

        // AdSense 주석 + <script>. **둘을 따로 센다.**
        // ⚠ 처음엔 "둘 중 하나라도 지워졌으면 통과"로 짰다가 실제로 당했다 —
        //   주석만 지워지고 <script>는 남았는데 검사가 통과했다(2026-08-31).
        //   ★ 가드가 가려지는 것은 가드가 없는 것보다 나쁘다.
        // ⚠ new RegExp + 템플릿 리터럴을 쓰지 않는다. `[\s\S]`가 `[sS]`로
        //   뭉개져 조용히 빗나갔다. 리터럴 정규식이면 그 실수가 불가능하다.
        out = cutOrThrow(out, /[ \t]*<!--\s*AdSense[\s\S]*?-->\n?/g, "AdSense 주석");
        out = cutOrThrow(
          out,
          /[ \t]*<script\b[^>]*googlesyndication[\s\S]*?<\/script>\n?/g,
          "AdSense <script>",
        );
        return out;
      },
    },

    // ② 산출물에서 광고 흔적을 검사하고, 방침 페이지 사본을 들어낸다.
    closeBundle() {
      const outDir = new URL("./dist-app/", import.meta.url).pathname
        .replace(/^\/([A-Za-z]:)/, "$1");

      // 방침 페이지(public/privacy/)에도 소유권 확인용 AdSense 태그가 있다.
      // 앱에서는 링크하지 않으므로(About이 배포된 https URL을 연다) 통째로 뺀다.
      const privacy = join(outDir, "privacy");
      if (existsSync(privacy)) rmSync(privacy, { recursive: true, force: true });

      // 서비스워커는 앱에서 등록하지 않는다(main.jsx). 파일도 남기지 않는다 —
      // APK 안의 죽은 파일은 다음 사람에게 "쓰이는 것"으로 읽힌다.
      const sw = join(outDir, "sw.js");
      if (existsSync(sw)) rmSync(sw, { force: true });

      // ★ 최종 관문 — 산출물 어디에도 광고 호스트가 없어야 한다.
      //   ①이 빗나가도 여기서 빌드가 죽는다. 두 겹으로 두는 이유는
      //   ①이 index.html만 보고, 광고 코드가 들어올 길은 그것만이 아니기 때문이다.
      const hits = [];
      walk(outDir, (file) => {
        if (!/\.(html|js|css|webmanifest|json)$/i.test(file)) return;
        if (readFileSync(file, "utf8").includes(AD_HOST)) hits.push(file);
      });
      if (hits.length) {
        throw new Error(
          `[pym] 앱 번들에 AdSense가 남아 있습니다:\n  ${hits.join("\n  ")}`,
        );
      }
    },
  };
}

/** 반드시 한 번은 지워져야 하는 치환. 안 걸리면 빌드를 세운다. */
function cutOrThrow(text, pattern, what) {
  const out = text.replace(pattern, "");
  if (out === text) {
    throw new Error(
      `[pym] index.html에서 ${what}을(를) 찾지 못했습니다. ` +
        "index.html이 바뀌었다면 vite.config.js의 정규식도 함께 고쳐야 합니다.",
    );
  }
  return out;
}

function walk(dir, visit) {
  if (!existsSync(dir)) return;
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, visit);
    else visit(full);
  }
}
