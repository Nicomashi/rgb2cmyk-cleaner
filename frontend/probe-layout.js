const intersects = (a, b, gap = 6) =>
  a.x < b.x + b.width + gap && a.x + a.width + gap > b.x &&
  a.y < b.y + b.height + gap && a.y + a.height + gap > b.y;

// Screen-space placement keeps labels readable at every image zoom level.
export function layoutProbeReadouts(points, width, height, reserved = []) {
  const box = { width: 140, height: 42 }, margin = 8;
  const visible = points.filter(p => p.x >= 0 && p.y >= 0 && p.x <= width && p.y <= height);
  const obstacles = [...reserved, ...visible.map(p => ({ x: p.x - 21, y: p.y - 21, width: 44, height: 46 }))];
  const placed = [];
  for (const p of visible) {
    const candidates = [];
    const add = (x, y) => {
      x = Math.max(margin, Math.min(width - box.width - margin, x));
      y = Math.max(margin, Math.min(height - box.height - margin, y));
      if (width < box.width + margin * 2 || height < box.height + margin * 2) return;
      const rect = { x, y, ...box };
      const dx = Math.max(x - p.x, 0, p.x - x - box.width);
      const dy = Math.max(y - p.y, 0, p.y - y - box.height);
      candidates.push({ ...rect, score: dx * dx + dy * dy });
    };
    // Prefer the closest side, then fan crowded groups into neighbouring rows.
    for (let row = 0; row <= Math.ceil(height / 50); row++) {
      for (const sign of row ? [-1, 1] : [1]) {
        const y = p.y - box.height / 2 + sign * row * 50;
        add(p.x + 28, y);
        add(p.x - box.width - 28, y);
      }
    }
    // A dense group may need another column. Search the remaining canvas too.
    for (let y = margin; y + box.height <= height - margin; y += 50)
      for (let x = margin; x + box.width <= width - margin; x += 148) add(x, y);
    candidates.sort((a, b) => a.score - b.score);
    const chosen = candidates.find(rect => ![...obstacles, ...placed].some(other => intersects(rect, other)));
    if (chosen) placed.push({ id: p.id, ...chosen });
  }
  return placed;
}
