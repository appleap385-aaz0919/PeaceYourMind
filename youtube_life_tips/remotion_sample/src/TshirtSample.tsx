import { Audio } from "@remotion/media";
import { loadFont } from "@remotion/fonts";
import {
  AbsoluteFill,
  CanvasImage,
  Composition,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "./tshirt-data.json";

await Promise.all([
  loadFont({
    family: "TshirtKorean",
    url: staticFile("generated/Malgun.ttf"),
    weight: "400",
  }),
  loadFont({
    family: "TshirtKorean",
    url: staticFile("generated/Malgun-Bold.ttf"),
    weight: "700",
  }),
]);
type Scene = (typeof data.scenes)[number];

const PhotoScene = ({ scene, index }: { scene: Scene; index: number }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: 44,
          top: 48,
          fontSize: 24,
          color: "#b9cdb0",
          fontWeight: 700,
          letterSpacing: 1,
        }}
      >
        살림 한 수
      </div>
      <div
        style={{
          position: "absolute",
          right: 44,
          top: 51,
          fontSize: 22,
          color: "#bec8b9",
        }}
      >
        AI 재현
      </div>
      <div
        data-heading
        style={{
          position: "absolute",
          left: 44,
          right: 40,
          top: 112,
          fontSize: 43,
          lineHeight: 1.32,
          fontWeight: 700,
          letterSpacing: -1.1,
          whiteSpace: "pre-line",
        }}
      >
        {scene.title}
      </div>
      <div
        data-photo
        style={{
          position: "absolute",
          left: 24,
          top: 278,
          width: 672,
          height: 672,
          background: "#d5c2a7",
          overflow: "hidden",
        }}
      >
        <CanvasImage
          src={staticFile(scene.image)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            scale: interpolate(
              frame,
              [0, Math.max(fps, scene.frames - 1)],
              [0.985, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            ),
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: 44,
          top: 1194,
          fontSize: 22,
          color: "#a5b39f",
        }}
      >
        {String(index + 1).padStart(2, "0")} / {data.scenes.length}
      </div>
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
        left: 44,
        right: 44,
        top: 981,
        height: 185,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 32,
        lineHeight: 1.5,
        textAlign: "center",
        fontWeight: 700,
        wordBreak: "keep-all",
        overflowWrap: "break-word",
      }}
    >
      {chunk?.text}
    </div>
  );
};

const Progress = () => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        left: 44,
        right: 44,
        top: 1237,
        height: 4,
        background: "#495143",
      }}
    >
      <div
        style={{
          height: 4,
          width: `${(100 * frame) / (data.frames - 1)}%`,
          background: "#b9cdb0",
        }}
      />
    </div>
  );
};

export const TshirtSample = () => (
  <AbsoluteFill
    style={{
      background: "#20281f",
      color: "#f9f6ee",
      fontFamily: "TshirtKorean",
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
        <PhotoScene scene={scene} index={i} />
      </Sequence>
    ))}
    {data.chunks.map((chunk, i) => (
      <Sequence
        key={chunk.audio}
        name={`가방 내레이션 ${i + 1}`}
        from={chunk.from}
        durationInFrames={chunk.frames}
      >
        <Audio src={staticFile(chunk.audio)} />
      </Sequence>
    ))}
    <Captions />
    <Progress />
  </AbsoluteFill>
);

export const TshirtComposition = () => (
  <Composition
    id="TshirtBag"
    component={TshirtSample}
    durationInFrames={data.frames}
    fps={15}
    width={720}
    height={1280}
  />
);
