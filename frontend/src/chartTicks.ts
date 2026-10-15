/** A small, shared scale for the native charts and saved report charts. */
export function chartTicks(values: number[], percent = false) {
  const finite = values.filter(Number.isFinite);
  const minimum = Math.min(0, ...finite);
  const maximum = Math.max(0, ...finite);
  if (minimum === maximum) return {minimum: 0, maximum: 1, ticks: [0, 0.25, 0.5, 0.75, 1], label: (value: number) => percent ? `${value * 100}%` : String(value)};
  const span = maximum - minimum || 1;
  const rough = span / 3;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 4, 5, 10].map(part => part * magnitude).find(candidate => candidate >= rough) || 10 * magnitude;
  const first = Math.floor(minimum / step) * step;
  const last = Math.max(first + step, Math.ceil(maximum / step) * step);
  const count = Math.round((last - first) / step);
  const ticks = Array.from({length: count + 1}, (_, index) => Number((first + index * step).toPrecision(12)));
  const decimals = (size: number) => Math.min(16, Math.max(0, -Math.floor(Math.log10(size)) + (size / 10 ** Math.floor(Math.log10(size)) % 1 ? 1 : 0)));
  const compact = (value: number, unit: number, suffix: string) => `${Number((value / unit).toFixed(decimals(step / unit))).toLocaleString('en-US', {maximumFractionDigits: 16})}${suffix}`;
  const label = (value: number) => {
    if (percent) return `${Number((value * 100).toFixed(decimals(step * 100))).toLocaleString('en-US', {maximumFractionDigits: 16})}%`;
    const abs = Math.abs(value);
    if (abs >= 1e9 && step >= 1e6) return compact(value, 1e9, 'b');
    if (abs >= 1e6 && step >= 1e3) return compact(value, 1e6, 'm');
    if (abs >= 1e3 && step >= 1) return compact(value, 1e3, 'k');
    return Number(value.toFixed(decimals(step))).toLocaleString('en-US', {maximumFractionDigits: 16});
  };
  return {minimum: first, maximum: last, ticks, label};
}
