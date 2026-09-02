import { gsap, ScrollTrigger } from './gsap';

/**
 * Motion vocabulary for the schematic landing.
 *
 * The rules are deliberately narrow: short durations, expo/quart easing,
 * small translations, and no blur, scale-bounce or glow. Anything that
 * draws attention to the animation itself is out — the page should feel
 * like an instrument settling, not a title sequence.
 */
export const EASE = 'expo.out';
export const EASE_RULE = 'power2.inOut';

const prefersReduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Fade + 10px rise for any element carrying `data-reveal`. */
export function revealOnScroll(selector = '[data-reveal]', stagger = 0.06) {
  if (prefersReduced()) return;

  gsap.utils.toArray<HTMLElement>(selector).forEach((el) => {
    gsap.fromTo(
      el,
      { y: 10, autoAlpha: 0 },
      {
        y: 0,
        autoAlpha: 1,
        duration: 0.7,
        ease: EASE,
        immediateRender: false,
        scrollTrigger: { trigger: el, start: 'top 90%', once: true },
      },
    );
  });

  void stagger;
}

/** Staggered variant for grids and lists sharing one trigger. */
export function revealGroup(selector: string, trigger: string, stagger = 0.05) {
  if (prefersReduced()) return;

  gsap.fromTo(
    selector,
    { y: 10, autoAlpha: 0 },
    {
      y: 0,
      autoAlpha: 1,
      duration: 0.6,
      ease: EASE,
      stagger,
      immediateRender: false,
      scrollTrigger: { trigger, start: 'top 88%', once: true },
    },
  );
}

/** Hairlines that draw themselves in — the signature move of a ruled layout. */
export function drawRules(selector: string, trigger: string, stagger = 0.05) {
  if (prefersReduced()) return;

  gsap.fromTo(
    selector,
    { scaleX: 0 },
    {
      scaleX: 1,
      duration: 0.9,
      ease: EASE_RULE,
      stagger,
      transformOrigin: 'left center',
      immediateRender: false,
      scrollTrigger: { trigger, start: 'top 88%', once: true },
    },
  );
}

/** Meter / bar fills. Flat colour, no glow, driven off the same easing. */
export function fillMeters(selector: string, trigger: string, axis: 'x' | 'y' = 'x') {
  if (prefersReduced()) return;

  const from = axis === 'x' ? { scaleX: 0 } : { scaleY: 0 };
  const to = axis === 'x' ? { scaleX: 1 } : { scaleY: 1 };

  gsap.fromTo(selector, from, {
    ...to,
    duration: 1,
    ease: EASE,
    stagger: 0.08,
    transformOrigin: axis === 'x' ? 'left center' : 'bottom center',
    immediateRender: false,
    scrollTrigger: { trigger, start: 'top 85%', once: true },
  });
}

/** Tabular numerals counting up. Values stay monospaced so nothing reflows. */
export function countUp(el: HTMLElement, target: number, suffix = '') {
  if (prefersReduced()) {
    el.textContent = `${target}${suffix}`;
    return;
  }

  const obj = { v: 0 };
  gsap.to(obj, {
    v: target,
    duration: 1.1,
    ease: 'power2.out',
    scrollTrigger: { trigger: el, start: 'top 92%', once: true },
    onUpdate: () => {
      el.textContent = `${Math.round(obj.v)}${suffix}`;
    },
  });
}

export { ScrollTrigger };
