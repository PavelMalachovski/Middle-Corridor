import { describe, expect, it } from "vitest";
import { isSoftwareRenderer } from "./webgl";

describe("isSoftwareRenderer", () => {
  it("узнаёт программные рендеры", () => {
    expect(isSoftwareRenderer("Google SwiftShader")).toBe(true);
    expect(isSoftwareRenderer("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)))")).toBe(
      true,
    );
    expect(isSoftwareRenderer("Mesa/X.org, llvmpipe (LLVM 15.0.7, 256 bits)")).toBe(true);
    expect(isSoftwareRenderer("Microsoft Basic Render Driver (Software)")).toBe(true);
  });

  it("настоящие GPU и неизвестность — не программный", () => {
    expect(isSoftwareRenderer("ANGLE (Apple, Apple M2, OpenGL 4.1)")).toBe(false);
    expect(isSoftwareRenderer("Mali-G78 MC14")).toBe(false);
    expect(isSoftwareRenderer("NVIDIA GeForce RTX 3060/PCIe/SSE2")).toBe(false);
    expect(isSoftwareRenderer(null)).toBe(false);
    expect(isSoftwareRenderer("")).toBe(false);
  });
});
