/**
 * 테스트 공용 도구 — **소스를 검사하는 테스트는 전부 여기를 지난다.**
 *
 * [왜 파일로 뺐는가 — 같은 함정에 세 번 걸렸다]
 *   이 앱의 소스에는 설명 주석이 길게 붙어 있고, 그 주석이 코드를 **인용한다.**
 *   원문 그대로 검사하면 실행되는 코드가 아니라 그것을 설명한 문장이 잡힌다.
 *
 *     1회차  위기 화면 검사가 "MediaToggle을 import하지 않는다"는 **주석**을
 *            위반으로 잡았다 (거짓 실패)
 *     2회차  토글 밑줄 검사가 "전에는 borderBottom 단축을 썼다"는 주석을
 *            위반으로 잡았다 (거짓 실패)
 *     3회차  폴백 헤더 검사가 "지금: 딱 맞는 건 아니지만…"이라는 개정 이력
 *            주석을 통과 근거로 삼았다 — **이번엔 거짓 통과였다.**
 *            실제 렌더 문구를 XXX로 바꿔도 테스트가 통과했다.
 *
 *   1·2회차는 시끄럽게 실패해서 바로 드러났지만 3회차는 조용했다.
 *   거짓 통과가 더 위험하다 — 검사가 있다고 믿는 채로 검사가 없는 상태가 된다.
 *
 * ⚠ **소스를 읽는 새 테스트는 예외 없이 readSource()를 쓴다.**
 *   readFileSync로 .jsx/.js를 직접 읽는 코드가 test/ 안에 있으면 그건 이
 *   함정에 다시 걸릴 자리다. sourcesAreStripped 테스트가 그것을 감시한다.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "..", "src");

/** 주석을 걷어낸다. 검사 대상은 실행되는 코드지 그것을 설명한 문장이 아니다. */
export function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

/**
 * src/ 아래 파일을 주석 없이 읽는다.
 * @param {...string} parts src 기준 경로 조각 (예: "components", "VideoList.jsx")
 */
export function readSource(...parts) {
  return stripComments(readFileSync(join(SRC, ...parts), "utf8"));
}

/**
 * app/ 루트의 설정 파일(vite.config.js 등)을 주석 없이 읽는다.
 *
 * ⚠ src/ 밖이라 readSource()가 닿지 않지만 **사정은 똑같다** —
 *   vite.config.js의 주석이 base 경로를 그대로 인용한다(`/PeaceYourMind/`).
 *   그래서 `includes("/PeaceYourMind/")` 같은 느슨한 검사는 코드를 지워도
 *   주석만으로 통과한다. 3회차 거짓 통과와 정확히 같은 모양이다.
 * ★ 원본 읽기는 이 파일 안에만 둔다. test/ 쪽에서 readFileSync로 .js를 직접
 *   읽으면 sourcesAreStripped 검사가 막는다 — 그 통로가 여기다.
 */
export function readAppFile(...parts) {
  return stripComments(readFileSync(join(here, "..", ...parts), "utf8"));
}

/** 주석까지 그대로 필요할 때만. 쓰는 곳에 이유를 적을 것. */
export function readSourceRaw(...parts) {
  return readFileSync(join(SRC, ...parts), "utf8");
}
