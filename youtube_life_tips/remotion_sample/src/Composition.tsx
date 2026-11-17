import React from "react";
import { Audio } from "@remotion/media";
import { loadFont } from "@remotion/fonts";
import {
  AbsoluteFill,
  Composition,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "./sample-data.json";

await Promise.all([
  loadFont({
    family: "SampleKorean",
    url: staticFile("generated/Malgun.ttf"),
    weight: "400",
  }),
  loadFont({
    family: "SampleKorean",
    url: staticFile("generated/Malgun-Bold.ttf"),
    weight: "700",
  }),
]);

const C = {
  ink: "#26322d",
  muted: "#68736c",
  paper: "#f6f3e9",
  wood: "#c79b68",
  darkWood: "#967046",
  lightWood: "#e8cda6",
  wax: "#edaf20",
  blue: "#287886",
  red: "#af493d",
};
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
type Scene = (typeof data.scenes)[number];

const Label = ({
  x,
  y,
  children,
  color = C.ink,
  size = 29,
  anchor = "middle",
}: {
  x: number;
  y: number;
  children: React.ReactNode;
  color?: string;
  size?: number;
  anchor?: "middle" | "start" | "end";
}) => (
  <text
    x={x}
    y={y}
    fill={color}
    fontSize={size}
    fontWeight={700}
    textAnchor={anchor}
  >
    {children}
  </text>
);

const Defs = () => (
  <defs>
    <pattern id="wood" width="110" height="35" patternUnits="userSpaceOnUse">
      <rect width="110" height="35" fill={C.wood} />
      <path
        d="M0 10 Q30 1 60 12 T110 10 M0 29 Q50 19 110 29"
        stroke="#b58a5b"
        fill="none"
        strokeWidth="2"
      />
    </pattern>
    <marker
      id="arrow"
      markerWidth="10"
      markerHeight="10"
      refX="8"
      refY="5"
      orient="auto-start-reverse"
    >
      <path d="M1 1 L9 5 L1 9" fill="none" stroke={C.blue} strokeWidth="2" />
    </marker>
  </defs>
);

const Candle = ({
  x,
  y,
  scale = 1,
  tilt = 0,
}: {
  x: number;
  y: number;
  scale?: number;
  tilt?: number;
}) => (
  <g transform={`translate(${x} ${y}) scale(${scale}) rotate(${tilt} 24 138)`}>
    <path
      d="M3 20 Q24 7 45 20 L45 132 Q25 147 3 132 Z"
      fill="#fffdf2"
      stroke="#a79e87"
      strokeWidth="3"
    />
    <ellipse
      cx="24"
      cy="20"
      rx="21"
      ry="7"
      fill="#eee7d6"
      stroke="#a79e87"
      strokeWidth="2"
    />
    <path
      d="M24 20 L26 7"
      stroke={C.ink}
      strokeWidth="3"
      strokeLinecap="round"
    />
    <path
      d="M11 39 L11 119"
      stroke="white"
      strokeWidth="5"
      strokeLinecap="round"
    />
  </g>
);

const Cabinet = ({
  open = 0,
  empty = false,
}: {
  open?: number;
  empty?: boolean;
}) => (
  <g>
    <ellipse cx="351" cy="487" rx="234" ry="24" fill="#26322d" opacity=".08" />
    <path
      d="M172 161 L475 161 L548 119 L244 119 Z"
      fill={C.lightWood}
      stroke={C.darkWood}
      strokeWidth="4"
    />
    <path
      d="M475 161 L548 119 L548 419 L475 464 Z"
      fill={C.darkWood}
      stroke={C.darkWood}
      strokeWidth="4"
    />
    <rect
      x="172"
      y="161"
      width="303"
      height="303"
      rx="5"
      fill="url(#wood)"
      stroke={C.darkWood}
      strokeWidth="4"
    />
    <rect x="195" y="190" width="254" height="239" fill="#75563a" />
    <path d="M205 399 L438 399 L438 427 L205 427 Z" fill={C.lightWood} />
    {(empty || open > 0.7) && (
      <path
        d="M303 329 L319 329 L319 403 L340 403 L340 329 L357 329 L357 421 L303 421 Z"
        fill={C.wood}
        stroke={C.paper}
        strokeWidth="3"
      />
    )}
    {!empty && (
      <g transform={`translate(${-open * 130} ${open * 90})`}>
        <path
          d="M205 219 L451 219 L425 315 L180 315 Z"
          fill={C.lightWood}
          stroke={C.darkWood}
          strokeWidth="3"
        />
        <path
          d="M205 219 L451 219 L451 287 L205 287 Z"
          fill="#ab8051"
          stroke={C.darkWood}
          strokeWidth="3"
        />
        <rect
          x="180"
          y="283"
          width="273"
          height="145"
          rx="4"
          fill="url(#wood)"
          stroke={C.darkWood}
          strokeWidth="4"
        />
        <ellipse cx="317" cy="354" rx="18" ry="13" fill={C.darkWood} />
        <path
          d="M196 304 H436 M196 408 H436"
          stroke={C.lightWood}
          opacity=".6"
          strokeWidth="3"
        />
      </g>
    )}
  </g>
);

const CrossSection = ({
  gap = 0,
  wax = false,
  clean = false,
  progress = 0,
}: {
  gap?: number;
  wax?: boolean;
  clean?: boolean;
  progress?: number;
}) => (
  <g>
    <Label x={360} y={58} color={C.muted} size={25}>
      정면 단면 · 구조를 확대한 예시
    </Label>
    <g transform={`translate(0 ${-gap})`}>
      <rect
        x="118"
        y="208"
        width="484"
        height="36"
        rx="3"
        fill="url(#wood)"
        stroke={C.darkWood}
        strokeWidth="3"
      />
      <rect
        x="294"
        y="244"
        width="132"
        height="90"
        rx="2"
        fill={C.lightWood}
        stroke={C.darkWood}
        strokeWidth="3"
      />
      <Label x={360} y={181} size={28}>
        서랍 밑면
      </Label>
      {wax && (
        <path
          d="M295 251 V331 H425 V251"
          fill="none"
          stroke={C.wax}
          strokeWidth="7"
        />
      )}
    </g>
    <g transform={`translate(0 ${gap})`}>
      <path
        d="M250 244 H290 V338 H430 V244 H470 V382 H250 Z"
        fill="url(#wood)"
        stroke={C.darkWood}
        strokeWidth="3"
      />
      <path
        d="M290 249 V338 H430 V249"
        fill="none"
        stroke={C.blue}
        strokeWidth="5"
      />
      {wax && (
        <path
          d="M291 251 V337 H429 V251"
          fill="none"
          stroke={C.wax}
          strokeWidth="7"
        />
      )}
    </g>
    <Label x={115} y={320 - gap} color={C.darkWood} size={27}>
      나무 막대
    </Label>
    <path
      d={`M202 ${310 - gap} H270 L312 ${290 - gap}`}
      stroke={C.darkWood}
      fill="none"
      strokeWidth="3"
    />
    <circle cx={312} cy={290 - gap} r={4} fill={C.darkWood} />
    <Label x={360} y={496 + gap} color={C.blue} size={29}>
      수납장 안쪽 홈
    </Label>
    <path
      d={`M465 ${486 + gap} H513 V${298 + gap} H434`}
      stroke={C.blue}
      fill="none"
      strokeWidth="3"
      markerEnd="url(#arrow)"
    />
    {clean && (
      <>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <circle
            key={i}
            cx={282 + i * 31}
            cy={327 + gap}
            r="4"
            fill={C.darkWood}
            opacity={1 - progress}
          />
        ))}
        <g
          transform={`translate(${292 + 100 * progress} ${285 - gap}) rotate(-15)`}
        >
          <rect
            width="48"
            height="35"
            rx="6"
            fill="#fffdf4"
            stroke={C.blue}
            strokeWidth="3"
          />
          <path d="M8 8 L39 27 M7 23 L38 8" stroke="#c1cbc2" strokeWidth="2" />
        </g>
        <g
          transform={`translate(${282 + 120 * progress} ${310 + gap}) rotate(12)`}
        >
          <rect
            width="48"
            height="35"
            rx="6"
            fill="#fffdf4"
            stroke={C.blue}
            strokeWidth="3"
          />
          <path d="M8 8 L39 27 M7 23 L38 8" stroke="#c1cbc2" strokeWidth="2" />
        </g>
      </>
    )}
  </g>
);

const WaxApplication = ({
  target,
  progress,
}: {
  target: "drawer" | "groove";
  progress: number;
}) => {
  const x = 145 + 420 * progress;
  return (
    <g>
      <Label x={360} y={75} color={C.muted} size={26}>
        {target === "drawer"
          ? "서랍을 뒤집어 본 밑면"
          : "수납장 안쪽 홈을 위에서 본 예시"}
      </Label>
      <rect
        x="98"
        y="212"
        width="524"
        height="210"
        rx="8"
        fill={C.lightWood}
        stroke={C.darkWood}
        strokeWidth="4"
      />
      {target === "drawer" ? (
        <>
          <rect
            x="128"
            y="278"
            width="464"
            height="75"
            fill="url(#wood)"
            stroke={C.darkWood}
            strokeWidth="3"
          />
          <path d="M128 353 H592 V375 H128 Z" fill={C.darkWood} />
          <path
            d={`M140 355 H${145 + 420 * progress}`}
            stroke={C.wax}
            strokeWidth="11"
          />
          <Label x={360} y={480} color={C.darkWood} size={30}>
            서랍 밑에 붙은 나무 막대
          </Label>
          <Candle x={x - 24} y={215} tilt={-18} />
        </>
      ) : (
        <>
          <rect x="111" y="249" width="498" height="101" fill="#8c6b48" />
          <path
            d="M111 249 H609 M111 350 H609"
            stroke={C.blue}
            strokeWidth="6"
          />
          <path
            d={`M125 252 H${145 + 420 * progress}`}
            stroke={C.wax}
            strokeWidth="10"
          />
          <path
            d={`M125 347 H${145 + 420 * progress}`}
            stroke={C.wax}
            strokeWidth="7"
            opacity=".8"
          />
          <Label x={360} y={480} color={C.blue} size={30}>
            홈의 안쪽 면에만 발라요
          </Label>
          <Candle x={x - 24} y={112} tilt={-18} />
        </>
      )}
      <path
        d="M153 548 H568"
        stroke={C.blue}
        strokeWidth="4"
        markerEnd="url(#arrow)"
      />
      <Label x={360} y={596} color={C.blue} size={29}>
        길이 방향으로 얇게 문질러요
      </Label>
    </g>
  );
};

const Insert = ({ progress }: { progress: number }) => {
  const x = 62 + 282 * progress;
  return (
    <g>
      <Label x={360} y={72} size={26} color={C.muted}>
        위에서 본 이동 방향 · 구조 예시
      </Label>
      <rect
        x="323"
        y="222"
        width="315"
        height="177"
        rx="4"
        fill="url(#wood)"
        stroke={C.darkWood}
        strokeWidth="4"
      />
      <rect x="322" y="266" width="317" height="78" fill="#7f6344" />
      <path d="M323 267 H638 M323 343 H638" stroke={C.wax} strokeWidth="5" />
      <rect
        x={x}
        y="271"
        width="230"
        height="68"
        rx="3"
        fill={C.lightWood}
        stroke={C.darkWood}
        strokeWidth="3"
      />
      <path
        d={`M${x + 8} 275 H${x + 221} M${x + 8} 335 H${x + 221}`}
        stroke={C.wax}
        strokeWidth="4"
      />
      <Label x={480} y={460} size={29} color={C.blue}>
        수납장 안쪽 홈
      </Label>
      <Label x={x + 115} y={195} size={27} color={C.darkWood}>
        서랍 밑 막대
      </Label>
      <path
        d="M153 535 H562"
        stroke={C.blue}
        strokeWidth="4"
        markerEnd="url(#arrow)"
        markerStart="url(#arrow)"
      />
      <Label x={360} y={589} color={C.blue}>
        같은 방향으로 맞춰 끼워요
      </Label>
    </g>
  );
};

const Drawing = ({ scene }: { scene: Scene }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = interpolate(
    f,
    [0.7 * fps, Math.max(fps, scene.frames - fps)],
    [0, 1],
    clamp,
  );
  const section = scene.kind;
  let art: React.ReactNode;
  if (section === "hook")
    art = (
      <>
        <Cabinet open={0.35 + 0.12 * Math.sin(f * 0.28)} />
        <Candle x={550} y={350} />
        <Label x={360} y={573} color={C.blue}>
          집에 있는 양초, 접촉면에만
        </Label>
      </>
    );
  else if (section === "principle")
    art = (
      <>
        <CrossSection wax gap={0} />
        <Label x={360} y={595} color={C.darkWood} size={27}>
          노란 선 = 얇게 남은 왁스
        </Label>
      </>
    );
  else if (section === "exclude")
    art = (
      <>
        <rect
          x="89"
          y="196"
          width="237"
          height="76"
          rx="6"
          fill="#c8cfcc"
          stroke="#7d8984"
          strokeWidth="4"
        />
        <rect
          x="116"
          y="213"
          width="178"
          height="39"
          fill="#e6e9e6"
          stroke="#7d8984"
          strokeWidth="3"
        />
        {[140, 185, 230, 275].map((x) => (
          <circle key={x} cx={x} cy="232" r="7" fill="#7d8984" />
        ))}
        <path
          d="M405 228 Q467 169 609 215 L609 270 Q486 224 405 283 Z"
          fill="url(#wood)"
          stroke={C.darkWood}
          strokeWidth="4"
        />
        <path
          d="M505 209 L490 230 L516 241 L497 257"
          stroke={C.red}
          strokeWidth="6"
          fill="none"
        />
        <Label x={204} y={340}>
          금속 레일
        </Label>
        <Label x={506} y={340}>
          휘거나 갈라진 나무
        </Label>
        {[204, 506].map((x) => (
          <g key={x}>
            <circle
              cx={x}
              cy="431"
              r="38"
              stroke={C.red}
              strokeWidth="5"
              fill="none"
            />
            <path
              d={`M${x - 16} 415 L${x + 16} 447 M${x + 16} 415 L${x - 16} 447`}
              stroke={C.red}
              strokeWidth="5"
              strokeLinecap="round"
            />
          </g>
        ))}
        <Label x={360} y={567} color={C.red}>
          다른 점검·수선이 필요해요
        </Label>
      </>
    );
  else if (section === "remove")
    art = (
      <>
        <Cabinet open={p} />
        <g transform={`translate(${-p * 130} ${p * 90})`}>
          <path
            d="M199 434 Q228 463 259 434 M355 434 Q384 463 415 434"
            fill="none"
            stroke={C.blue}
            strokeWidth="7"
            strokeLinecap="round"
          />
        </g>
        <Label x={360} y={595} color={C.blue}>
          비운 서랍을 양손으로 받쳐요
        </Label>
      </>
    );
  else if (section === "structure")
    art = <CrossSection gap={55 * (1 - Math.min(1, p * 1.3))} />;
  else if (section === "clean")
    art = <CrossSection gap={45} clean progress={p} />;
  else if (section === "candle")
    art = (
      <>
        <Candle x={300} y={151} scale={2.5} />
        <Label x={360} y={553} color={C.blue} size={34}>
          불 없이 · 녹이지 않고
        </Label>
      </>
    );
  else if (section === "wax-drawer")
    art = <WaxApplication target="drawer" progress={p} />;
  else if (section === "wax-groove")
    art = <WaxApplication target="groove" progress={p} />;
  else if (section === "assemble") {
    const split = scene.chunks[0].frames;
    art =
      f < split ? (
        <Insert
          progress={interpolate(
            f,
            [0, Math.max(1, split - fps)],
            [0, 1],
            clamp,
          )}
        />
      ) : (
        <>
          <Cabinet open={0.25 + 0.2 * Math.sin(((f - split) / fps) * 2.4)} />
          <Label x={360} y={574} color={C.blue}>
            가볍게 여닫아 움직임을 확인
          </Label>
        </>
      );
  } else
    art = (
      <>
        <Cabinet empty />
        <circle
          cx="357"
          cy="306"
          r="57"
          fill={C.paper}
          stroke={C.red}
          strokeWidth="5"
        />
        <path
          d="M334 281 V327 M350 273 V327 M366 278 V327 M382 290 V326 Q382 354 351 354 Q335 354 326 338 L314 316 Q310 303 320 306 L334 319"
          fill="none"
          stroke={C.red}
          strokeWidth="7"
          strokeLinecap="round"
        />
        <Label x={360} y={565} color={C.red}>
          여전히 걸리면 수선을 맡기세요
        </Label>
      </>
    );
  return (
    <svg
      width="720"
      height="650"
      viewBox="0 0 720 650"
      style={{
        position: "absolute",
        top: 303,
        left: 0,
        fontFamily: "SampleKorean",
      }}
    >
      <Defs />
      {art}
    </svg>
  );
};

const SceneView = ({ scene, index }: { scene: Scene; index: number }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{ opacity: interpolate(frame, [0, 0.22 * fps], [0.55, 1], clamp) }}
    >
      <div
        style={{
          position: "absolute",
          top: 62,
          left: 52,
          fontSize: 25,
          fontWeight: 700,
          letterSpacing: 2,
          color: C.blue,
        }}
      >
        살림 한 수
      </div>
      <div
        style={{
          position: "absolute",
          top: 64,
          right: 52,
          fontSize: 23,
          color: C.muted,
        }}
      >
        {String(index + 1).padStart(2, "0")} / 11
      </div>
      <div
        style={{
          position: "absolute",
          top: 121,
          left: 52,
          right: 45,
          fontSize: 49,
          lineHeight: 1.32,
          fontWeight: 700,
          whiteSpace: "pre-line",
          letterSpacing: -1.7,
        }}
      >
        {scene.title}
      </div>
      <Drawing scene={scene} />
    </AbsoluteFill>
  );
};

const Captions = () => {
  const frame = useCurrentFrame();
  const chunk = data.chunks.find(
    (c) => frame >= c.from && frame < c.from + c.frames,
  );
  return (
    <div
      data-caption
      style={{
        position: "absolute",
        top: 991,
        left: 52,
        right: 52,
        height: 193,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 32,
        lineHeight: 1.55,
        textAlign: "center",
        wordBreak: "keep-all",
        overflowWrap: "break-word",
        fontWeight: 700,
      }}
    >
      {chunk?.text}
    </div>
  );
};

const Progress = () => {
  const f = useCurrentFrame();
  return (
    <>
      <div
        style={{
          position: "absolute",
          top: 1215,
          left: 52,
          width: 616,
          height: 4,
          background: "#dcded2",
        }}
      >
        <div
          style={{
            width: `${(100 * f) / (data.frames - 1)}%`,
            height: 4,
            background: C.blue,
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          top: 1230,
          left: 52,
          fontSize: 20,
          color: C.muted,
        }}
      >
        원리와 작업 순서를 보여주는 설명용 그림
      </div>
    </>
  );
};

export const DrawerSample = () => (
  <AbsoluteFill
    style={{
      background: C.paper,
      color: C.ink,
      fontFamily: "SampleKorean",
      overflow: "hidden",
    }}
  >
    {data.scenes.map((scene, i) => (
      <Sequence
        key={scene.kind}
        name={scene.title.replace("\n", " ")}
        from={scene.from}
        durationInFrames={scene.frames}
      >
        <SceneView scene={scene} index={i} />
      </Sequence>
    ))}
    {data.chunks.map((chunk, i) => (
      <Sequence
        key={chunk.audio}
        name={`내레이션 ${i + 1}`}
        from={chunk.from}
        durationInFrames={chunk.frames}
      >
        <Audio src={staticFile(chunk.audio)} />
      </Sequence>
    ))}
    <div
      style={{
        position: "absolute",
        top: 976,
        left: 52,
        right: 52,
        height: 2,
        background: "#d9ddcf",
      }}
    />
    <Captions />
    <Progress />
  </AbsoluteFill>
);

export const MyComposition = () => (
  <Composition
    id="DrawerWax"
    component={DrawerSample}
    durationInFrames={data.frames}
    fps={15}
    width={720}
    height={1280}
  />
);
