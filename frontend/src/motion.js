import { useEffect, useRef, useState } from "react";

const REDUCED = "(prefers-reduced-motion: reduce)";

function prefersReduced() {
  return typeof window !== "undefined" && window.matchMedia(REDUCED).matches;
}

/** Прогон числа от текущего значения к целевому: цифры на дашборде «набираются». */
export function useCountUp(target, duration = 900) {
  const [value, setValue] = useState(prefersReduced() ? target : 0);
  const from = useRef(prefersReduced() ? target : 0);

  useEffect(() => {
    if (prefersReduced()) {
      from.current = target;
      setValue(target);
      return undefined;
    }

    const start = performance.now();
    const origin = from.current;
    let raf;

    const step = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - p) ** 3;
      setValue(Math.round(origin + (target - origin) * eased));
      if (p < 1) raf = requestAnimationFrame(step);
      else from.current = target;
    };

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return value;
}

/**
 * Возвращает true через кадр после монтирования. Нужен, чтобы диаграммы
 * стартовали с нулевой ширины и доезжали до значения через CSS-переход.
 */
export function useRevealed(delay = 80) {
  const [revealed, setRevealed] = useState(prefersReduced());

  useEffect(() => {
    if (prefersReduced()) return undefined;
    const timer = setTimeout(() => setRevealed(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  return revealed;
}
