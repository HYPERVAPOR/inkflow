import { useCurrentFrame, useVideoConfig } from "remotion";
import { useEffect, useRef } from "react";

export interface ShaderTransitionProps {
  src: string;
  shaderName: string;
  duration: number;
  toColor?: [number, number, number];
}

const vertexShaderSource = `#version 300 es
in vec2 a_position;
in vec2 a_texCoord;
out vec2 v_texCoord;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
  v_texCoord = a_texCoord;
}`;

const fragmentMix = `#version 300 es
precision highp float;
in vec2 v_texCoord;
uniform sampler2D u_source;
uniform float u_progress;
uniform vec3 u_toColor;
out vec4 outColor;
void main() {
  vec4 sourceColor = texture(u_source, v_texCoord);
  outColor = mix(sourceColor, vec4(u_toColor, 1.0), u_progress);
}`;

const fragmentCrossZoom = `#version 300 es
precision highp float;
in vec2 v_texCoord;
uniform sampler2D u_source;
uniform float u_progress;
uniform vec3 u_toColor;
out vec4 outColor;
void main() {
  vec2 center = vec2(0.5, 0.5);
  float zoom = 1.0 + u_progress * 0.5;
  vec2 zoomed = center + (v_texCoord - center) / zoom;
  vec4 sourceColor = texture(u_source, zoomed);
  outColor = mix(sourceColor, vec4(u_toColor, 1.0), u_progress);
}`;

const fragmentPixelate = `#version 300 es
precision highp float;
in vec2 v_texCoord;
uniform sampler2D u_source;
uniform float u_progress;
uniform vec3 u_toColor;
out vec4 outColor;
float grid = 1.0 + u_progress * 99.0;
vec2 pixelated = floor(v_texCoord * grid) / grid + 0.5 / grid;
void main() {
  vec4 sourceColor = texture(u_source, pixelated);
  outColor = mix(sourceColor, vec4(u_toColor, 1.0), u_progress);
}`;

const shaders: Record<string, string> = {
  mix: fragmentMix,
  cross_zoom: fragmentCrossZoom,
  pixelate: fragmentPixelate,
};

export const ShaderTransition: React.FC<ShaderTransitionProps> = ({
  src,
  shaderName,
  duration,
  toColor = [0, 0, 0],
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const progress = Math.min(frame / (duration * fps), 1);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl2");
    if (!gl) {
      console.warn("WebGL2 not available, shader transition disabled");
      return;
    }

    const fragmentSource = shaders[shaderName] || fragmentMix;

    const compileShader = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error(gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    };

    const vertexShader = compileShader(gl.VERTEX_SHADER, vertexShaderSource);
    const fragmentShader = compileShader(gl.FRAGMENT_SHADER, fragmentSource);
    if (!vertexShader || !fragmentShader) return;

    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error(gl.getProgramInfoLog(program));
      return;
    }
    gl.useProgram(program);

    const positions = new Float32Array([
      -1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1,
    ]);
    const texCoords = new Float32Array([0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1]);

    const positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
    const positionLocation = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(positionLocation);
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);

    const texCoordBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, texCoordBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, texCoords, gl.STATIC_DRAW);
    const texCoordLocation = gl.getAttribLocation(program, "a_texCoord");
    gl.enableVertexAttribArray(texCoordLocation);
    gl.vertexAttribPointer(texCoordLocation, 2, gl.FLOAT, false, 0, 0);

    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA,
      1,
      1,
      0,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      new Uint8Array([0, 0, 0, 255])
    );
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.src = src;
    image.onload = () => {
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    };

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(gl.getUniformLocation(program, "u_source"), 0);
    gl.uniform1f(gl.getUniformLocation(program, "u_progress"), progress);
    gl.uniform3f(
      gl.getUniformLocation(program, "u_toColor"),
      toColor[0] / 255,
      toColor[1] / 255,
      toColor[2] / 255
    );
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }, [frame, src, shaderName, progress, width, height, toColor]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    />
  );
};
