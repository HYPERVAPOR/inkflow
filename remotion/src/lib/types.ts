export interface Layout {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
}

export interface Animation {
  type?: "none" | "fade_in" | "slide_in" | "scale_in" | "draw" | "grow";
  duration?: number;
  delay?: number;
  direction?: "left" | "right" | "top" | "bottom";
  easing?: "linear" | "ease" | "ease_in_out";
}

export interface CompositionElement {
  id: string;
  type:
    | "seedream_image"
    | "text"
    | "chart_line"
    | "chart_bar"
    | "chart_pie"
    | "map"
    | "shape"
    | "video";
  props: Record<string, unknown>;
  layout: Layout;
  animation?: Animation;
}

export interface TransitionConfig {
  type: "none" | "fade" | "slide" | "shader" | "seedance";
  name?: string;
  duration: number;
  direction?: "left" | "right" | "top" | "bottom";
}

export interface CompositionDefinition {
  id: string;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  elements: CompositionElement[];
  transition?: TransitionConfig;
  background?: string;
}

export interface CompositionData {
  compositions: CompositionDefinition[];
}
