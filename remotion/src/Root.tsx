import { Composition } from "remotion";
import { Infographic } from "./compositions/Infographic";
import type { CompositionData } from "./lib/types";

let compositionData: CompositionData = { compositions: [] };
try {
  // composition.json is generated at runtime by the Python pipeline.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  compositionData = require("../public/composition.json");
} catch {
  // No composition.json available during development/build.
}

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {compositionData.compositions.map((comp) => (
        <Composition
          key={comp.id}
          id={comp.id}
          component={Infographic as unknown as React.ComponentType<Record<string, unknown>>}
          defaultProps={{
            elements: comp.elements,
            transition: comp.transition,
            background: comp.background,
          }}
          durationInFrames={comp.durationInFrames}
          fps={comp.fps}
          width={comp.width}
          height={comp.height}
        />
      ))}
    </>
  );
};
