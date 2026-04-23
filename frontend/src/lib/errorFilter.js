// Suppress noise coming from browser extensions (MetaMask, wallet providers, etc.)
// These errors originate outside our app and should not reach the console or crash the UI.

const EXTENSION_NOISE_PATTERNS = [
  /MetaMask/i,
  /chrome-extension:\/\//i,
  /moz-extension:\/\//i,
  /safari-web-extension:\/\//i,
  /web3\b/i,
  /ethereum\b/i,
  /Cannot redefine property: ethereum/i,
  /evmAsk\.js/i,
  /inpage\.js/i,
  /contentscript\.js/i,
  /Non-Error promise rejection captured/i,
  /ResizeObserver loop/i,
];

function isExtensionNoise(value) {
  if (!value) return false;
  const str = typeof value === "string" ? value : value.message || value.stack || String(value);
  return EXTENSION_NOISE_PATTERNS.some((p) => p.test(str));
}

export function installExtensionErrorFilter() {
  // Catch uncaught errors
  window.addEventListener(
    "error",
    (event) => {
      const src = event.filename || "";
      if (isExtensionNoise(src) || isExtensionNoise(event.error) || isExtensionNoise(event.message)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return false;
      }
      return undefined;
    },
    true
  );

  // Catch unhandled rejections (MetaMask often throws these on hostile pages)
  window.addEventListener(
    "unhandledrejection",
    (event) => {
      if (isExtensionNoise(event.reason)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true
  );

  // Filter console errors as well, since extensions sometimes write directly
  const originalError = window.console.error;
  window.console.error = function filteredError(...args) {
    const text = args.map((a) => (a && a.message) || String(a)).join(" ");
    if (isExtensionNoise(text)) return;
    originalError.apply(window.console, args);
  };
}
