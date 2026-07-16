import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import type { Animation } from "../lib/types";

export interface TextRevealProps {
  text: string;
  style?: React.CSSProperties;
  animation?: Animation;
}

export const TextReveal: React.FC<TextRevealProps> = ({
  text,
  style,
  animation,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const duration = animation?.duration ?? 0.5;
  const delay = animation?.delay ?? 0;
  const startFrame = delay * fps;
  const endFrame = startFrame + duration * fps;

  const opacity = interpolate(
    frame,
    [startFrame, endFrame],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const translateY = interpolate(
    frame,
    [startFrame, endFrame],
    [20, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: "100%",
        height: "100%",
        opacity,
        transform: `translateY(${translateY}px)`,
        ...style,
      }}
    >
      {text}
    </div>
  );
};
