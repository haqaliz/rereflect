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
