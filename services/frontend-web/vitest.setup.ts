import '@testing-library/jest-dom';

// ResizeObserver polyfill for Recharts ResponsiveContainer in jsdom
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// scrollIntoView polyfill for jsdom
window.HTMLElement.prototype.scrollIntoView = function () {};
