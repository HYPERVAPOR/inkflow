import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import type { Animation } from "../lib/types";

export interface ChartProps {
  type: "line" | "bar" | "pie";
  data: number[];
  style?: React.CSSProperties;
  animation?: Animation;
  options?: Record<string, string | string[]>;
}

export const Chart: React.FC<ChartProps> = ({
  type,
  data,
  style,
  animation,
  options,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const duration = animation?.duration ?? 1.5;
  const delay = animation?.delay ?? 0;
  const startFrame = delay * fps;
  const endFrame = startFrame + duration * fps;

  const progress = interpolate(frame, [startFrame, endFrame], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const width = typeof style?.width === "number" ? style.width : 800;
  const height = typeof style?.height === "number" ? style.height : 400;
  const padding = 40;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  const maxValue = Math.max(...data, 1);

  const lineColor =
    typeof options?.color === "string" ? options.color : "#3b82f6";
  const getColor = (i: number) =>
    typeof options?.colors?.[i] === "string"
      ? (options.colors[i] as string)
      : `hsl(${(i * 360) / data.length}, 70%, 60%)`;

  if (type === "line") {
    const points = data.map((value, i) => {
      const x = padding + (i / (data.length - 1)) * chartWidth;
      const y = padding + chartHeight - (value / maxValue) * chartHeight * progress;
      return `${x},${y}`;
    });

    return (
      <svg width={width} height={height} style={style}>
        <polyline
          points={points.join(" ")}
          fill="none"
          stroke={lineColor}
          strokeWidth={4}
        />
        {data.map((value, i) => {
          const x = padding + (i / (data.length - 1)) * chartWidth;
          const y =
            padding + chartHeight - (value / maxValue) * chartHeight * progress;
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={5}
              fill={lineColor}
            />
          );
        })}
      </svg>
    );
  }

  if (type === "bar") {
    const barWidth = chartWidth / data.length * 0.6;
    const spacing = chartWidth / data.length;

    return (
      <svg width={width} height={height} style={style}>
        {data.map((value, i) => {
          const barHeight = (value / maxValue) * chartHeight * progress;
          const x = padding + i * spacing + (spacing - barWidth) / 2;
          const y = padding + chartHeight - barHeight;
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={barWidth}
              height={barHeight}
              fill={getColor(i)}
            />
          );
        })}
      </svg>
    );
  }

  // Pie chart
  const total = data.reduce((a, b) => a + b, 0) || 1;
  const radius = Math.min(chartWidth, chartHeight) / 2;
  const centerX = width / 2;
  const centerY = height / 2;
  let currentAngle = 0;

  return (
    <svg width={width} height={height} style={style}>
      {data.map((value, i) => {
        const sliceAngle = (value / total) * 360 * progress;
        const startAngle = (currentAngle * Math.PI) / 180;
        currentAngle += sliceAngle;
        const endAngle = (currentAngle * Math.PI) / 180;

        const x1 = centerX + radius * Math.cos(startAngle);
        const y1 = centerY + radius * Math.sin(startAngle);
        const x2 = centerX + radius * Math.cos(endAngle);
        const y2 = centerY + radius * Math.sin(endAngle);

        const largeArcFlag = sliceAngle > 180 ? 1 : 0;

        return (
          <path
            key={i}
            d={`M ${centerX} ${centerY} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2} Z`}
            fill={getColor(i)}
          />
        );
      })}
    </svg>
  );
};
