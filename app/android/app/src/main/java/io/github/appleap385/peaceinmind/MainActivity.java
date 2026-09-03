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
        web.post(() -> pushInset(web));
    }

    /** 마지막으로 넣은 값. 같은 값을 반복해 넣지 않는다(레이아웃마다 불린다). */
    private String lastPushed = null;

    private void pushInset(View v) {
        try {
            WindowInsetsCompat insets = ViewCompat.getRootWindowInsets(v);
            if (insets == null) return;
            int inset = insets.getInsets(WindowInsetsCompat.Type.systemBars()).bottom;

            int[] loc = new int[2];
            v.getLocationOnScreen(loc);
            int webBottom = loc[1] + v.getHeight();

            int displayHeight = displayHeight();
            if (displayHeight <= 0) return;

            int cut = Math.max(0, displayHeight - webBottom); // P
            float density = getResources().getDisplayMetrics().density;
            if (density <= 0) return;
            float dp = Math.max(0, inset - cut) / density;

            final String value = dp + "px";
            if (value.equals(lastPushed)) return;
            lastPushed = value;
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
