import { useEffect, useRef } from "react";

export function usePolling(fn: () => void, ms: number): void {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    const id = setInterval(() => fnRef.current(), ms);
    return () => clearInterval(id);
  }, [ms]);
}
