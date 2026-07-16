import { Img, staticFile } from "remotion";

export interface SeedreamImageProps {
  src: string;
  style?: React.CSSProperties;
}

export const SeedreamImage: React.FC<SeedreamImageProps> = ({ src, style }) => {
  return (
    <Img
      src={staticFile(src)}
      style={{
        ...style,
        objectFit: "cover",
      }}
    />
  );
};
