import { useCurrentFrame, useVideoConfig, AbsoluteFill } from "remotion";
import { SeedreamImage } from "./SeedreamImage";
import { TextReveal } from "./TextReveal";
import { Chart } from "./Chart";
import { Map } from "./Map";
import { ShaderTransition } from "./ShaderTransition";
import { computeAnimationStyle } from "../lib/easing";
import { getTransitionComponent } from "../lib/transitions";
import type { CompositionElement, TransitionConfig } from "../lib/types";

export interface InfographicProps {
  elements: CompositionElement[];
  transition?: TransitionConfig;
  background?: string;
}

export const Infographic: React.FC<InfographicProps> = ({
  elements,
  transition,
  background,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const bgStyle: React.CSSProperties = background
    ? { background }
    : { backgroundColor: "#ffffff" };

  const renderElement = (element: CompositionElement) => {
    const props = element.props;
    const commonStyle: React.CSSProperties = {
      position: "absolute",
      left: element.layout.x ?? 0,
      top: element.layout.y ?? 0,
      width: element.layout.width ?? width,
      height: element.layout.height ?? height,
      ...computeAnimationStyle(frame, fps, element.animation),
    };

    switch (element.type) {
      case "seedream_image":
        return (
          <SeedreamImage
            key={element.id}
            src={props.src as string}
            style={commonStyle}
          />
        );
      case "text":
        return (
          <TextReveal
            key={element.id}
            text={props.text as string}
            style={{
              ...commonStyle,
              fontSize: (props.fontSize as number | undefined) ?? 48,
              color: (props.color as string | undefined) ?? "#000000",
              fontFamily: (props.fontFamily as string | undefined) ?? "Noto Sans SC",
              textAlign: (props.textAlign as CanvasTextAlign) ?? "center",
            }}
            animation={element.animation}
          />
        );
      case "chart_line":
      case "chart_bar":
      case "chart_pie":
        return (
          <Chart
            key={element.id}
            type={element.type.replace("chart_", "") as "line" | "bar" | "pie"}
            data={props.data as number[]}
            style={commonStyle}
            animation={element.animation}
            options={props.options as Record<string, string | string[]> | undefined}
          />
        );
      case "map":
        return (
          <Map
            key={element.id}
            src={props.src as string}
            style={commonStyle}
            animation={element.animation}
          />
        );
      case "shape":
        return (
          <div
            key={element.id}
            style={{
              ...commonStyle,
              backgroundColor: (props.color as string | undefined) ?? "#000000",
              borderRadius: (props.borderRadius as number | undefined) ?? 0,
            }}
          />
        );
      default:
        return null;
    }
  };

  const TransitionComponent = transition
    ? getTransitionComponent(transition)
    : null;

  const firstImageSrc = elements.find((e) => e.type === "seedream_image")?.props
    .src as string | undefined;

  return (
    <AbsoluteFill style={bgStyle}>
      {elements.map(renderElement)}
      {TransitionComponent && transition && transition.type !== "shader" && (
        <TransitionComponent frame={frame} fps={fps} config={transition} />
      )}
      {transition && transition.type === "shader" && firstImageSrc && (
        <ShaderTransition
          src={firstImageSrc}
          shaderName={transition.name || "mix"}
          duration={transition.duration}
        />
      )}
    </AbsoluteFill>
  );
};
