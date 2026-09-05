// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

function Bomb({ explode }: { explode: boolean }) {
  if (explode) throw new Error("boom");
  return <span>живой</span>;
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
      true;
    vi.spyOn(console, "error").mockImplementation(() => {}); // React дублирует ошибку в консоль
  });
  afterEach(() => vi.restoreAllMocks());

  it("показывает fallback вместо упавшего поддерева и восстанавливается по reset", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    let explode = true;
    const render = async () =>
      act(() =>
        root.render(
          <ErrorBoundary
            scope="test"
            fallback={(e, reset) => (
              <button type="button" onClick={reset}>
                {e.message}
              </button>
            )}
          >
            <Bomb explode={explode} />
          </ErrorBoundary>,
        ),
      );

    await render();
    expect(container.textContent).toBe("boom");

    explode = false;
    await render(); // новые пропсы сами по себе не снимают ошибку
    expect(container.textContent).toBe("boom");

    await act(() => container.querySelector("button")?.click());
    expect(container.textContent).toBe("живой");
  });

  it("сосед упавшего поддерева продолжает жить", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(() =>
      root.render(
        <>
          <ErrorBoundary scope="a" fallback={() => <i>упало</i>}>
            <Bomb explode />
          </ErrorBoundary>
          <ErrorBoundary scope="b" fallback={() => <i>упало</i>}>
            <Bomb explode={false} />
          </ErrorBoundary>
        </>,
      ),
    );
    expect(container.textContent).toBe("упаложивой");
  });
});
