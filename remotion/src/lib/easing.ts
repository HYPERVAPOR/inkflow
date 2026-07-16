import { interpolate, Easing } from "remotion";
import type { Animation } from "./types";

export const computeAnimationStyle = (
  frame: number,
  fps: number,
  animation?: Animation
): React.CSSProperties => {
  if (!animation || animation.type === "none") {
    return {};
  }

  const duration = animation.duration ?? 0.5;
  const delay = animation.delay ?? 0;
  const startFrame = delay * fps;
  const endFrame = startFrame + duration * fps;

  const progress = interpolate(frame, [startFrame, endFrame], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  switch (animation.type) {
    case "fade_in":
      return { opacity: progress };
    case "slide_in": {
      const direction = animation.direction ?? "bottom";
      const distance = 50;
      const transforms: Record<string, string> = {
        left: `translateX(${-distance * (1 - progress)}px)`,
        right: `translateX(${distance * (1 - progress)}px)`,
        top: `translateY(${-distance * (1 - progress)}px)`,
        bottom: `translateY(${distance * (1 - progress)}px)`,
      };
      return { opacity: progress, transform: transforms[direction] };
    }
    case "scale_in":
      return { opacity: progress, transform: `scale(${progress})` };
    case "draw":
    case "grow":
      return { opacity: progress };
    default:
      return {};
  }
};
