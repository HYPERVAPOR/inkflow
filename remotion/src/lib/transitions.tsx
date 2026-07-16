import { interpolate } from "remotion";
import type { TransitionConfig } from "./types";

export interface TransitionComponentProps {
  frame: number;
  fps: number;
  config: TransitionConfig;
}

const FadeTransition: React.FC<TransitionComponentProps> = ({ frame, fps, config }) => {
  const opacity = interpolate(frame, [0, config.duration * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundColor: "#000",
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};

const SlideTransition: React.FC<TransitionComponentProps> = ({ frame, fps, config }) => {
  const progress = interpolate(frame, [0, config.duration * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const direction = config.direction ?? "right";
  const distance = 100 * progress;
  const translateX =
    direction === "left" ? -distance : direction === "right" ? distance : 0;
  const translateY =
    direction === "top" ? -distance : direction === "bottom" ? distance : 0;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundColor: "#000",
        transform: `translateX(${translateX}%) translateY(${translateY}%)`,
        opacity: 1 - progress,
        pointerEvents: "none",
      }}
    />
  );
};

export const getTransitionComponent = (
  config: TransitionConfig
): React.FC<TransitionComponentProps> | null => {
  switch (config.type) {
    case "fade":
      return FadeTransition;
    case "slide":
      return SlideTransition;
    case "shader":
    case "seedance":
    default:
      return null;
  }
};
