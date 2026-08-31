import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// service worker 등록 실패는 사용자에게 알리지 않는다.
// 오프라인 캐싱이 안 될 뿐이고, 앱 자체는 그대로 동작한다.
//
// [⛔ 앱(Capacitor)에서는 등록하지 않는다 — 2026-08-31 결정]
//   서비스워커가 웹에서 하는 일은 셋이고, 앱에서는 둘이 이미 끝나 있다.
//     앱 셸    APK 안에 있다. 네트워크를 아예 타지 않는다
//     장 본문   APK 안에 있다(__KRV_BASE__ = /krv/). 첫 실행부터 오프라인으로 열린다
//     썸네일   ⚠ 이것만 남는다. 그런데 이득 하나를 위해 웹뷰의 서비스워커
//             동작을 따로 검증해야 하고, APK 자산을 상대로 도는 캐시 사본이
//             하나 더 생긴다. **얻는 것보다 검증 비용이 크다**
//   vite.config.js가 dist-app에서 sw.js 파일 자체도 지운다.
if (!__IS_APP__ && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {});
  });
}
