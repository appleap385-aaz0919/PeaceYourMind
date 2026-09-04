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

import { readSource } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const read = (...p) => readFileSync(join(root, ...p), "utf8");

/**
 * ⛔ src/ 소스는 **readSource()로 읽는다** — 주석을 걷어낸 것이다.
 *   이 파일의 새 검사는 `IS_APP` 분기를 찾는데, 아래 두 파일의 **주석이 그 코드를
 *   그대로 인용한다.** 원문으로 읽으면 조건을 지워도 주석만으로 통과한다
 *   (helpers.js 상단의 3회차 거짓 통과와 같은 모양이다).
 */
const appJsx = readSource("App.jsx");
const tabsJsx = readSource("components", "ResultTabs.jsx");
const aboutJsx = readSource("components", "About.jsx");

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

/* --- ⛔ 앱 전용 요소가 웹으로 새지 않는다 (2026-09-04 · 2.122) --------------
 *
 * [무엇이 있었나]
 *   결과 화면 탭 행에 「구절 알림」 토글을 얹으면서 `__IS_APP__` 분기가 빠졌다.
 *   웹에는 로컬 알림이 없어 **눌러도 아무 일이 없는 토글**이 모바일 웹에 나갔고,
 *   그 상태로 배포됐다(2026-09-03 run 77).
 *
 * [⛔ 왜 293건이 다 통과했나 — 검사의 방향이 한쪽뿐이었다]
 *   · 순수 함수 검사   무엇이 그려지는지 모른다
 *   · 소스 모양 검사   "그 파일에 조건이 있나"만 본다. **조건이 없는 새 파일**은
 *                    검사 대상이 아니라서 안 걸린다
 *   · 산출물 검사      **앱 쪽에만** 있었다(AdSense가 앱에 남았나).
 *                    웹 쪽 산출물 검사는 **아예 없었다**
 *   ★ "웹 전용이 앱으로" 방향만 있었고 "앱 전용이 웹으로" 방향은 무방비였다.
 *     아래 검사가 그 방향을 채운다.
 */

test("웹 빌드에 **산출물 가드**가 걸려 있다 (앱 전용 요소 검사)", () => {
  assert.ok(viteConfig.includes("function webBuildGuards()"), "웹 가드가 없다");
  assert.ok(
    viteConfig.includes("IS_APP ? appBuildGuards() : webBuildGuards()"),
    "웹 빌드에 가드가 등록되지 않는다 — 있어도 안 돈다",
  );
  assert.ok(
    viteConfig.includes("웹 번들에 **앱 전용 요소**가 남아 있습니다"),
    "산출물 검사가 사라졌다",
  );
});

test("가드가 보는 표식에 알림 토글과 토스트가 들어 있다", () => {
  // ⚠ 표식은 **산출물에서 확인한 모양**이다. 소스 모양을 넣으면 번들러가 바꾼 뒤
  //   안 걸리고, 그때는 조용히 통과한다.
  for (const needle of [
    'role:"switch"',
    "aria-label",
    "정해진 시각에 구절 한 절을 보내드릴게요",
    "기기 설정에서 알림을 켜 주세요",
  ]) {
    assert.ok(viteConfig.includes(needle), `가드 표식에 ${needle}이 없다`);
  }
});

test("⛔ 가드가 **가려지지 않는다** — 산출물을 못 읽으면 빌드가 선다", () => {
  // 가드가 있는 것처럼 보이면서 아무것도 안 보는 것이 가장 나쁜 결과다.
  // 그래서 "반드시 있어야 하는 문구"를 함께 찾고, 못 찾으면 던진다.
  assert.ok(viteConfig.includes("MUST_EXIST"), "양성 대조가 없다");
  assert.ok(
    viteConfig.includes("웹 가드가 산출물을 못 읽었습니다"),
    "산출물을 못 읽어도 통과한다 — 가드가 가려진다",
  );
});

test("★ 알림 토글이 **두 겹으로** 앱에서만 그려진다", () => {
  // ① 주는 쪽 — App이 웹에서는 notify를 아예 안 준다.
  assert.ok(
    /const notify = IS_APP \? \{ on: notifyOn, onToggle: toggleNotify \} : null;/.test(appJsx),
    "App이 웹에서도 notify를 준다 — 토글이 그려진다",
  );
  // ② 그리는 쪽 — **컴파일 시점 상수**여야 번들러가 마크업을 접는다.
  //   `notify` 하나만으로 막으면 그것은 런타임 조건이라 웹 산출물에 markup이 남는다.
  assert.ok(
    /\{IS_APP && notify \? \(/.test(tabsJsx),
    "ResultTabs가 런타임 조건만으로 막는다 — 웹 산출물에 토글 markup이 남는다",
  );
});

test("★ About이 쓰는 것과 **같은 조건**이다 (새 조건을 만들지 않았다)", () => {
  const IDIOM = 'const IS_APP = typeof __IS_APP__ === "boolean" ? __IS_APP__ : false;';
  for (const [name, src] of [
    ["About.jsx", aboutJsx],
    ["App.jsx", appJsx],
    ["ResultTabs.jsx", tabsJsx],
  ]) {
    assert.ok(src.includes(IDIOM), `${name}이 다른 조건을 쓴다`);
  }
  // ⛔ 플러그인 존재 여부 같은 **다른 판단**으로 갈리지 않는다. 그러면 웹/앱이
  //   빌드가 아니라 실행 시점에 갈리고, 번들러가 아무것도 못 접는다.
  for (const [name, src] of [["App.jsx", appJsx], ["ResultTabs.jsx", tabsJsx]]) {
    assert.ok(
      !/window\.Capacitor|isNativePlatform|navigator\.userAgent/.test(src),
      `${name}이 런타임으로 플랫폼을 판단한다`,
    );
  }
});

/* --- 업로드 키 서명 (2026-09-04 · 2.125) -----------------------------------
 *
 * ⛔ 키도 비밀번호도 **저장소 밖**에 있다. 그래서 여기서 볼 수 있는 것은
 *   "밖에 두는 구조가 살아 있는가"와 "없을 때 릴리스가 서는가"뿐이다.
 *   실제 서명 여부는 첫 AAB 업로드로 콘솔의 인증서 지문이 확인해 준다.
 */

const appGradle = read("android", "app", "build.gradle");
const gitignore = read("..", ".gitignore");

test("⛔ 업로드 키 경로를 **저장소 밖**에서 읽는다", () => {
  assert.ok(
    appGradle.includes("project.findProperty(PYM_KEYSTORE_POINTER)"),
    "gradle이 키 위치를 gradle property로 받지 않는다",
  );
  assert.ok(
    appGradle.includes('def PYM_KEYSTORE_POINTER = "pymKeystoreProperties"'),
    "포인터 이름이 바뀌었다 — 문서·견본과 갈린다",
  );
  // ⛔ 저장소 안의 고정 경로를 읽으면 안 된다. admob.properties와 다른 점이다.
  assert.ok(
    !/rootProject\.file\(\s*"keystore\.properties"\s*\)/.test(appGradle),
    "키 설정을 저장소 안에서 읽는다 — 비밀번호가 든 파일은 밖에 있어야 한다",
  );
});

test("⛔ 키·비밀번호 파일이 .gitignore 무늬로 막혀 있다 (이중 방어)", () => {
  for (const pat of ["*.jks", "*.keystore", "*.p12", "keystore.properties*"]) {
    assert.ok(gitignore.includes(pat), `.gitignore에 ${pat} 무늬가 없다`);
  }
  assert.ok(
    gitignore.includes("!app/android/keystore.properties.example"),
    "견본이 무늬에 걸려 추적되지 않는다",
  );
});

test("★ 키가 없을 때 — **release는 서고 debug는 돈다**", () => {
  assert.ok(appGradle.includes("verifyReleaseSigning"), "서명 게이트가 없다");
  // ⛔ configuration 시점에 throw하면 debug까지 죽는다. task 시점이어야 한다.
  assert.ok(
    /tasks\.register\("verifyReleaseSigning"\)/.test(appGradle),
    "서명 검사가 task가 아니다 — configuration에서 세우면 debug까지 죽는다",
  );
  assert.ok(
    appGradle.includes("dependsOn verifyNoDemoAdIds, verifyReleaseSigning"),
    "assembleRelease/bundleRelease 둘 다에 게이트가 걸려 있지 않다",
  );
  // ★ AAB를 함께 막는지 — Play가 받는 것은 AAB다.
  assert.ok(
    /it\.name in \["assembleRelease", "bundleRelease"\]/.test(appGradle),
    "AAB(bundleRelease)가 게이트를 안 지난다",
  );
  // ⛔ 준비가 안 되면 signingConfig는 null이다. 빈 config를 물리면 AGP가
  //   무엇을 해야 하는지 말하지 않는 메시지로 죽는다.
  assert.ok(
    appGradle.includes("signingConfig ksReady ? signingConfigs.release : null"),
    "키가 없을 때 signingConfig를 비우지 않는다",
  );
});

test("★ 게이트가 보는 것 넷 — 파일 존재 · 값 채움 · 견본값 · 경로 실재", () => {
  assert.ok(appGradle.includes("ksLoaded"), "파일 존재를 안 본다");
  for (const k of ["storeFile", "storePassword", "keyAlias", "keyPassword"]) {
    assert.ok(appGradle.includes(`ksProps.getProperty("${k}"`), `${k}를 안 읽는다`);
  }
  assert.ok(
    appGradle.includes('def PYM_KEYSTORE_SENTINEL = "<<CHANGE_ME>>"'),
    "견본값 검사가 없다 — 안 채운 채로 서명 시도가 나간다",
  );
  assert.ok(
    /new File\(sf\)\.isFile\(\)/.test(appGradle),
    "키 파일이 실제로 있는지 안 본다",
  );
  // ⚠ 비밀번호는 trim하지 않는다 — 공백도 비밀번호의 일부다.
  assert.ok(
    appGradle.includes("storePassword ksStorePassword"),
    "비밀번호를 가공해서 넘긴다 — 공백이 잘리면 원인 모를 서명 실패가 된다",
  );
});
