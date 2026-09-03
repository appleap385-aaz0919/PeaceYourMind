package io.github.appleap385.peaceinmind;

import android.graphics.Point;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebView;

import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import com.getcapacitor.BridgeActivity;

/**
 * 웹에 **참 하단 인셋**을 넣어 준다 — 그것 하나만 한다 (HANDOFF 2.118 안 2).
 *
 * [왜 필요한가]
 *   `env(safe-area-inset-bottom)`은 갈래 A에서만 참이고 B·C에서는 0을 준다.
 *   그런데 배너는 세 갈래 모두 화면 아래끝에서 `인셋 + margin` 위에 앉는다.
 *   배경면이 배너를 가운데 담으려면 **웹 좌표계 안에 들어온 인셋**을 알아야 한다.
 *
 *     X = max(0, I − P)      I 화면 하단 시스템 인셋 · P 웹뷰가 아래에서 잘린 양
 *
 *   갈래 A·B(edge-to-edge)  P = 0   → X = I
 *   갈래 C(창이 바 밖)       P = I   → X = 0
 *   ★ 이 값이 오면 갈래 구분이 사라진다. 안 오면 웹이 옛 비대칭식으로 떨어진다.
 *
 * [⛔⛔ 인셋 디스패치에 **끼어들지 않는다** — 처음에 그러다 화면을 깼다]
 *   웹뷰에 setOnApplyWindowInsetsListener를 걸었더니 웹뷰의 **기본 인셋 처리가
 *   그 자리를 잃어** 뷰포트가 800 → 848dp로 늘었다(내비 바 밑까지 내려갔다).
 *   리스너를 달면 뷰의 기본 동작이 대신 건너뛰어진다.
 *   ★ 그래서 **레이아웃 변화만 보고 루트 인셋을 읽는다.** 체인에 안 들어간다.
 *   ⚠ 그 자리들에는 이미 임자가 있기도 하다 —
 *     캐패시터는 webView.getParent()(SystemBars.java), AdMob은 decorView
 *     (BannerExecutor.java). 읽기만 하면 둘 다 건드리지 않는다.
 *
 * [⛔ 화면 높이는 루트 뷰가 아니라 **디스플레이**에서 얻는다]
 *   갈래 C에서는 창이 시스템 바 밖이라 DecorView 높이가 화면 높이보다 작다.
 *   루트 뷰로 재면 P가 0으로 나와 X가 I가 되어 **정반대 값**이 된다.
 *
 * ⚠ 이 파일에 다른 용도를 얹지 말 것. 인셋 하나만 넘긴다.
 */
public class MainActivity extends BridgeActivity {

    /** 웹이 읽는 이름. ⛔ App.jsx의 readInsetBottomReal()과 짝이다. */
    private static final String CSS_VAR = "--inset-bottom-real";

    /** 값이 바뀌었다고 웹에 알린다. ⛔ App.jsx의 useInsetBottomReal()과 짝이다. */
    private static final String JS_EVENT = "pym:inset";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        final WebView web = getBridge().getWebView();
        if (web == null) return;

        /**
         * ⛔⛔ **인셋 디스패치에 끼어들지 않는다.**
         *   처음에 setOnApplyWindowInsetsListener를 웹뷰에 걸었더니 웹뷰의 **기본
         *   인셋 처리가 대신 건너뛰어져** 뷰포트가 800 → 848dp로 늘었다(내비 바
         *   밑까지 내려갔다). 리스너를 달면 뷰의 기본 동작이 그 자리를 잃는다.
         *   ★ 그래서 **읽기만 한다** — 레이아웃이 바뀔 때 루트 인셋을 조회할 뿐이라
         *     디스패치 체인을 건드리지 않는다. 캐패시터·AdMob의 리스너도 그대로다.
         */
        web.addOnLayoutChangeListener(
            (v, l, t, r, b, ol, ot, or_, ob) -> pushInset(v)
        );
        schedulePushes();
    }

    /**
     * ⚠⚠ **같은 값을 다시 넣지 않는 최적화를 두지 않는다.** 두 번 데었다 —
     *   ① 웹이 로드되면 넣어 둔 CSS 변수가 **사라진다.** 그때 레이아웃은 안 바뀌므로
     *     리스너가 안 불리고, "이미 넣었다"고 기억하면 다시 넣지 않는다.
     *   ② 그래서 값이 없는 채로 웹이 폴백(옛 비대칭식)에 머문다 —
     *     실측에서 배경면이 82가 아니라 **98dp**로 나왔다(2026-09-03).
     * ★ 그래서 **여러 번 넣는다.** 짧은 JS 한 줄이라 비용이 없고, 페이지 로드가
     *   언제 끝나든 마지막 푸시가 살아남는다.
     */
    private static final long[] RETRY_MS = { 0L, 400L, 1200L, 3000L };

    @Override
    public void onResume() {
        super.onResume();
        schedulePushes();
    }

    private void schedulePushes() {
        final WebView web = getBridge() == null ? null : getBridge().getWebView();
        if (web == null) return;
        for (long delay : RETRY_MS) {
            web.postDelayed(() -> pushInset(web), delay);
        }
    }

    private void pushInset(View v) {
        try {
            WindowInsetsCompat insets = ViewCompat.getRootWindowInsets(v);
            if (insets == null) return;
            int inset = insets.getInsets(WindowInsetsCompat.Type.systemBars()).bottom;

            float density = getResources().getDisplayMetrics().density;
            if (density <= 0) return;

            /**
             * ⛔⛔ **X = I − P 가 아니다.** 갈래 B에서 배너가 배경면 위로 튀어나와
             *   (위 −8dp) 실측으로 잡았다(2026-09-03).
             *
             *   배너 아래끝이 화면 바닥에서 얼마나 떠 있는가를 플러그인 소스로 풀면
             *     배너 = P + margin + (SDK ≥ 35 ? I : 0)
             *   이다. 뒤 항이 BannerExecutor의 인셋 리스너인데, **Android 15+ 에서만**
             *   돈다. 그런데 그 부모가 이미 P만큼 올라와 있으면 **인셋이 두 번 들어간다.**
             *
             *   배경면 아래끝은 P + X 이므로  아래 여백 = margin + (SDK≥35 ? I : 0) − X.
             *   그것이 margin이 되려면  **X = (SDK ≥ 35) ? I : 0**  이다.
             *
             *   실측으로 셋 다 맞았다 — 배너 아래끝이 세 갈래 모두 화면 바닥에서 64dp다.
             *     갈래 A  P=0  SDK35  X=48   갈래 B  P=24 SDK35  X=24
             *     갈래 C  P=48 SDK33  X=0
             * ⚠ 이 식은 **플러그인 동작에 매인다.** pluginPins.test.js가 버전을 못 박는
             *   이유가 이것이다 — 버전이 오르면 BannerExecutor를 다시 읽고 여기를 고친다.
             */
            boolean pluginAddsInset = Build.VERSION.SDK_INT >= 35;
            float dp = (pluginAddsInset ? inset : 0) / density;

            final String value = dp + "px";
            // ⛔ 값만 넣으면 **웹이 모른다.** 주입은 마운트 뒤에 오는데 리액트는
            //   resize에서만 다시 읽으므로, 알리지 않으면 폴백에 머문다 —
            //   실기기에서 배경면이 82가 아니라 122로 남는 것으로 드러났다.
            final String js =
                "document.documentElement.style.setProperty('" + CSS_VAR + "','" + value + "');"
                    + "window.dispatchEvent(new Event('" + JS_EVENT + "'))";
            v.post(() -> {
                WebView web = getBridge() == null ? null : getBridge().getWebView();
                if (web != null) web.evaluateJavascript(js, null);
            });
        } catch (Exception ignored) {
            // ⛔ 조용히 넘어간다 — 값이 안 오면 웹이 폴백(옛 비대칭식)으로 간다.
            //   그쪽은 음수가 안 되므로 화면이 깨지지 않는다.
        }
    }

    private int displayHeight() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                return getWindowManager().getCurrentWindowMetrics().getBounds().height();
            }
            Point size = new Point();
            getWindowManager().getDefaultDisplay().getRealSize(size);
            return size.y;
        } catch (Exception ignored) {
            return 0;
        }
    }
}
