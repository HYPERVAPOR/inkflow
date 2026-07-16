import { Img, staticFile } from "remotion";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import type { Animation } from "../lib/types";

export interface MapProps {
  src: string;
  style?: React.CSSProperties;
  animation?: Animation;
}

export const Map: React.FC<MapProps> = ({ src, style, animation }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const duration = animation?.duration ?? 1.0;
  const delay = animation?.delay ?? 0;
  const startFrame = delay * fps;
  const endFrame = startFrame + duration * fps;

  const scale = interpolate(frame, [startFrame, endFrame], [1.0, 1.1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <Img
      src={staticFile(src)}
      style={{
        ...style,
        objectFit: "cover",
        transform: `scale(${scale})`,
      }}
    />
  );
};
