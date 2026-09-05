/** Поделиться ссылкой: Web Share API на телефоне, иначе — в буфер обмена. */

export type ShareResult = "shared" | "copied" | "failed";

export async function shareLink(url: string, title: string): Promise<ShareResult> {
  const nav = navigator as Navigator & { share?: (data: ShareData) => Promise<void> };
  if (typeof nav.share === "function") {
    try {
      await nav.share({ title, url });
      return "shared";
    } catch (e) {
      if ((e as { name?: string }).name === "AbortError") return "failed"; // пользователь закрыл
      /* иначе — пробуем буфер */
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch {
    return "failed";
  }
}
