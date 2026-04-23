export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function round(value: number, decimals = 2): number {
  const power = 10 ** decimals;
  return Math.round(value * power) / power;
}
