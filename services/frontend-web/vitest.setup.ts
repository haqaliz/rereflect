import '@testing-library/jest-dom';

// ResizeObserver polyfill for Recharts ResponsiveContainer in jsdom
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// scrollIntoView polyfill for jsdom
window.HTMLElement.prototype.scrollIntoView = function () {};

// Radix UI pointer capture polyfill for jsdom
window.Element.prototype.hasPointerCapture = function () { return false; };
window.Element.prototype.setPointerCapture = function () {};
window.Element.prototype.releasePointerCapture = function () {};

// ─── No real network from tests ──────────────────────────────────────────────
//
// apiClient is an axios instance pointed at http://localhost:8000 (api-client.ts:4),
// and axios uses XMLHttpRequest under jsdom. A page under test that reaches an API
// module its suite forgot to mock therefore issues a genuine request. On a dev
// machine with the backend running that quietly succeeds or 401s; in CI it escapes
// into jsdom's dispatcher and surfaces as an *unhandled rejection*
// (`UND_ERR_INVALID_ARG`), which fails the whole run even when every assertion
// passed — exactly what happened on the first CI run of this suite.
//
// Rather than let the outcome depend on whether something happens to be listening
// on port 8000, fail such requests in-process. Axios's XHR adapter turns the
// `error` event into a normal rejected promise, which the calling component's
// existing .catch handles — so a missing mock shows up as an empty/error state in
// that one test, not as a process-level crash.
//
// This is a backstop, not a substitute for mocking: a suite that means to exercise
// an API call must still mock the module.
class BlockedXMLHttpRequest extends (window as any).XMLHttpRequest {
  send() {
    // Async so listeners registered after send() still fire, matching real XHR.
    setTimeout(() => {
      Object.defineProperty(this, 'readyState', { value: 4, configurable: true });
      this.dispatchEvent(new Event('readystatechange'));
      this.dispatchEvent(new Event('error'));
    }, 0);
  }
  // jsdom would otherwise try to open a real connection on abort/timeout paths.
  abort() {}
}

Object.defineProperty(window, 'XMLHttpRequest', {
  writable: true,
  configurable: true,
  value: BlockedXMLHttpRequest,
});

// Same reasoning for anything that reaches for fetch directly.
if (!('__rereflectFetchBlocked' in globalThis)) {
  Object.defineProperty(globalThis, '__rereflectFetchBlocked', { value: true });
  globalThis.fetch = (async () => {
    throw new TypeError('fetch blocked in tests — mock the API module you are exercising');
  }) as typeof fetch;
}
