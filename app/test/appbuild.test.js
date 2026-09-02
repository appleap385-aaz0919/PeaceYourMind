/**
 * 앱(Capacitor) 빌드 계약 — 웹과 갈라지는 자리를 고정한다.
 *
 * [왜 빌드가 던지는 것만으로 부족한가]
 *   vite.config.js의 가드는 **앱을 빌드할 때** 동작한다. 그런데 가드 자체를
 *   지우면 아무 일도 일어나지 않는다. 여기서는 **가드가 있는지**를 검사한다.
 *   두 겹인 이유는 2026-08-31에 실제로 한 겹이 뚫렸기 때문이다 —
 *   주석만 지워지고 <script>는 남았는데 검사가 통과했다.
 *
 * ⚠ 이 파일은 소스의 **모양**을 본다. 동작은 빌드가 검사한다(npm run build:app).
 *   둘 다 필요하다: 모양 검사는 가드의 삭제를, 빌드 검사는 가드의 실패를 잡는다.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const read = (...p) => readFileSync(join(root, ...p), "utf8");

const viteConfig = read("vite.config.js");
const adsSrc = read("src", "lib", "ads.js");
const mainSrc = read("src", "main.jsx");
const capConfig = JSON.parse(read("capacitor.config.json"));
const pkg = JSON.parse(read("package.json"));

/* --- 광고: 앱에는 AdSense가 들어가지 않는다 -------------------------------
 *
 * AdSense 프로그램 정책이 앱 안의 AdSense를 명시적으로 금지한다
 * ("Integrated into a software application (does not apply to AdMob) ...").
 * 앱 광고는 AdMob으로 따로 간다(3단계). 그때까지 앱은 무광고다.
 *
 * ⛔ 지금 AD_SLOT이 빈 문자열이라 "어차피 안 뜬다"는 것은 근거가 되지 못한다.
 *   웹 심사가 통과해 값이 채워지는 날 **같은 소스가 앱에서도 광고를 켠다.**
 */
test("앱 빌드가 index.html에서 AdSense를 들어낸다", () => {
  assert.ok(
    viteConfig.includes("cutOrThrow"),
    "치환 실패를 잡는 함수가 없다 — 정규식이 빗나가도 조용히 통과한다",
  );
  assert.ok(
    viteConfig.includes("AdSense 주석") && viteConfig.includes("AdSense <script>"),
    "주석과 <script>를 따로 세지 않는다 — 한쪽만 지워져도 통과한다",
  );
  assert.ok(
    viteConfig.includes("googlesyndication"),
    "광고 호스트를 검사하지 않는다",
  );
});

test("앱 번들 산출물에 광고 흔적이 없는지 빌드가 최종 검사한다", () => {
  assert.ok(
    viteConfig.includes("앱 번들에 AdSense가 남아 있습니다"),
    "산출물 전수 검사가 사라졌다 — index.html 말고도 광고가 들어올 길이 있다",
  );
  assert.ok(
    viteConfig.includes('join(outDir, "privacy")'),
    "방침 페이지 사본을 빼지 않는다 — 그 안에도 소유권 확인 AdSense 태그가 있다",
  );
});

test("AD_SLOT이 앱에서는 무조건 빈 값이다", () => {
  assert.ok(
    /const IS_APP = typeof __IS_APP__ === "boolean"/.test(adsSrc),
    "앱 여부 분기가 없다",
  );
  assert.ok(
    /export const AD_SLOT = IS_APP \? "" : WEB_AD_SLOT;/.test(adsSrc),
    "AD_SLOT이 앱에서 강제로 비지 않는다 — 승인 후 값이 채워지면 앱에도 광고가 뜬다",
  );
  // 노드 테스트에는 vite 치환이 없다. 기본값이 웹이어야 웹 동작이 안 바뀐다.
  assert.ok(
    adsSrc.includes("? __IS_APP__ : false"),
    "치환이 없을 때의 기본값이 웹(false)이 아니다",
  );
});

/* --- 서비스워커: 앱에서는 등록하지 않는다 ---------------------------------
 * 앱 셸과 장 본문이 이미 APK 안에 있어 캐시할 것이 썸네일뿐이다.
 * 그 하나를 위해 웹뷰의 서비스워커 동작을 따로 검증할 이유가 없다.
 */
test("서비스워커를 앱에서는 등록하지 않는다", () => {
  assert.ok(
    mainSrc.includes('if (!__IS_APP__ && "serviceWorker" in navigator)'),
    "앱에서도 서비스워커를 등록한다",
  );
  assert.ok(
    viteConfig.includes('join(outDir, "sw.js")'),
    "앱 번들에서 sw.js 파일을 빼지 않는다 — 죽은 파일은 쓰이는 것으로 읽힌다",
  );
});

/* --- 산출물 경로: 앱 빌드가 웹 배포를 덮지 않는다 --------------------------
 * ⛔ deploy-app.yml이 `publish_dir: ./app/dist`를 웹에 올린다.
 *   앱 빌드가 같은 자리에 쓰면 앱 번들이 웹으로 배포될 수 있다.
 */
test("앱 빌드는 dist가 아니라 dist-app에 쓴다", () => {
  assert.ok(
    viteConfig.includes('outDir: IS_APP ? "dist-app" : "dist"'),
    "앱 빌드 산출물이 웹과 같은 디렉터리에 떨어진다 — 웹 배포를 덮을 수 있다",
  );
  assert.equal(
    capConfig.webDir,
    "dist-app",
    "Capacitor가 웹 배포용 dist를 APK에 싣는다",
  );
  assert.equal(pkg.scripts["build:app"], "vite build --mode capacitor");
});

/* --- Capacitor 설정 -------------------------------------------------------- */
test("Capacitor가 번들로 돈다 (server.url을 쓰지 않는다)", () => {
  // server.url을 실제 사이트로 두면 오프라인 첫 실행이 깨진다 — 설치 직후
  // 첫 실행이 곧 첫 방문이고, 네트워크가 없으면 아무것도 못 띄운다.
  // 그리고 Capacitor 공식 문서가 server.url을 "not intended for use in production"
  // 이라고 못박는다.
  assert.equal(capConfig.server, undefined, "server 블록이 생겼다 — 번들 실행이 깨진다");
  assert.equal(capConfig.appId, "io.github.appleap385.peaceinmind");
  assert.equal(capConfig.appName, "Peace in Mind");
});

test("앱은 영상 데이터만 원격에서 받는다", () => {
  // 번들에는 seed-videos.json만 있다. 최신 목록은 배치가 하루 2회 갱신하므로
  // 원격이어야 하고, 오리진이 localhost라 **절대 URL**이어야 한다.
  assert.ok(
    viteConfig.includes("`${SITE}data/`"),
    "앱의 데이터 경로가 절대 URL이 아니다 — localhost 오리진에서 상대 경로는 성립하지 않는다",
  );
  assert.ok(
    viteConfig.includes('IS_APP ? "/krv/"'),
    "장 본문 경로가 앱 기준이 아니다",
  );
});

/* --- AdMob 배너 단위: 잊을 자리를 없앤 뒤에도 가드가 남아 있는가 -------------
 *
 * [무엇을 막는가 — 2026-09-02 · HANDOFF 2.102]
 *   배너 단위 ID가 환경변수(ADMOB_BANNER_ID)였을 때, 그것을 빠뜨리고 릴리스를
 *   말면 값이 빈 문자열이 되어 **광고도 고지도 없는 앱**이 나가고
 *   **게이트가 전부 통과했다.** 데모 검사는 "데모가 있는가"만 보고,
 *   verses.test.js는 "소스에 값이 없는가"라는 **반대 방향**만 보기 때문이다.
 *
 * ⛔ 그래서 값을 App ID와 같은 파일로 옮겼고(가), 빌드가 없으면 선다(나).
 *   여기서는 그 두 장치가 **지워지지 않았는지**를 본다 —
 *   이 파일의 다른 검사들과 같은 이유다. 가드가 가려지는 것은 없는 것보다 나쁘다.
 */
test("배너 단위 ID를 환경변수가 아니라 admob.properties에서 읽는다", () => {
  assert.ok(
    viteConfig.includes("readAdmobBannerId"),
    "배너 단위를 읽는 함수가 없다",
  );
  assert.ok(
    viteConfig.includes('new URL("./android/admob.properties"'),
    "App ID와 같은 파일을 읽지 않는다 — 값 둘이 갈리면 되돌릴 때 퍼블리셔가 어긋난다",
  );
  assert.ok(
    !viteConfig.includes("process.env.ADMOB_BANNER_ID"),
    "환경변수가 되살아났다 — 잊을 자리를 없앤 것이 이 변경의 요점이다",
  );
});

test("배너 단위가 비면 앱 빌드가 선다", () => {
  // ⛔ 빈 값으로 조용히 가지 않는다. 실패를 빌드로 당겨 오는 것이 요점이다.
  assert.ok(
    /admob\.bannerId[\s\S]{0,400}?throw new Error/.test(viteConfig),
    "형식 검사 뒤에 throw가 없다 — 빈 값이 조용히 통과한다",
  );
  assert.ok(
    // String.raw 를 쓴다 — 보통 문자열이면 \d 가 d 로 뭉개져
    //   **검사가 조용히 통과한다.** vite.config.js의 [\s\S] 사고와 같은 모양이다.
    viteConfig.includes(String.raw`ca-app-pub-\d+\/\d+`),
    "단위 ID 형식 검사가 없다 — App ID(~)를 넣어도 통과한다",
  );
});

test("릴리스 게이트가 '실제 단위가 있는가'도 본다", () => {
  const gradle = read("android", "app", "build.gradle");
  assert.ok(
    gradle.includes("pymAdmobBannerId"),
    "gradle이 배너 단위를 읽지 않는다",
  );
  assert.ok(
    gradle.includes("hasUnit"),
    "번들에 실제 단위가 실렸는지 보는 검사가 없다 — 값이 없으면 데모 검사는 통과한다",
  );
});
