# Login art & diagonal fade — tuning guide

The auth portal (`/signin`, `/join`, `/forgot-password`) is a painting on the left
dissolving diagonally into the cream page the form sits on. Three independent knobs
control how it looks. This doc exists mainly because the asset's crop command is not
recoverable from the repo — the source PNG lives outside it.

## 1. Framing — which part of the painting is visible

`theCommonsWeb/src/app/(portal)/PortalShell.tsx`

```tsx
className="object-cover object-[50%_center]"
```

The X percentage slides the visible window through the painting. **Higher = window
moves right = more of the left of the tree is cut off.**

| value | trunk lands at (1440×900 viewport) |
|-------|-----------------------------------|
| 20%   | 13.4% across the viewport |
| 34%   | 10.1% |
| 50%   | 6.4% |
| **64%** (current) | **~3.1%** |
| 70%   | 1.8% |

Total travel is ~23% of viewport width. That only works because the asset is cut
deliberately wider than the panel — see below.

### Vertical framing

The image is height-bound under `object-fit: cover` — its rendered height already
matches the container, so `object-position`'s Y axis has nothing to slide through on
its own. Vertical movement instead comes from a `scale-y` + `-translate-y` pair on the
same `<Image>`:

```tsx
className="scale-y-[118%] -translate-y-[5%] object-cover object-[80%_center]"
```

`scale-y-[118%]` stretches the painting taller only — a deliberate distortion (the
tree reads slightly elongated), left as a knob because it also over-fills the
container by ~9% top and bottom. `-translate-y-[5%]` spends part of that overflow to
push the visible window up — more of the ground/roots at the bottom stay hidden, less
empty canvas shows above the tree. Negative values move the image up, positive move it
down. **Keep `|translate-y|` at or under half of `(scale-y - 100)`** (so up to ~9% at
`scale-y-[118%]`) — past that the bottom edge runs out of overflow and exposes
background instead of painting. Horizontal zoom is untouched by this — that's still
purely `object-position` X on the wide asset, above. `overflow-hidden` on the
`.portal-art` wrapper is required for this to clip instead of spilling out of the
panel.

## 2. The asset — for moves bigger than the knob above

`theCommonsWeb/public/login-tree.webp`, generated from the original painting:

```bash
cwebp -crop 1810 88 2785 1720 -resize 2400 0 -q 80 \
  ~/Downloads/commonsloginbase.png -o theCommonsWeb/public/login-tree.webp
```

`-crop x y w h` on the 4611×1877 original, then resized. Constraints:

- **Avoid the canvas frame edges** in the source photo: dark pixels at `x >= 4606`,
  `y <= ~80`, and `y >= ~1868`. Cropping into them puts a hard dark line on the panel.
- **Keep the output much wider than tall.** The panel is height-bound, so extra width
  becomes travel for `object-position` rather than shrinking the tree. At 2400×1483
  the panel uses ~1849px of the width, leaving ~551px of slack.

> **Next.js caches optimized images by path.** Re-cutting the file without changing its
> name serves the stale version locally until you `rm -rf theCommonsWeb/.next/cache/images`.
> Production is unaffected — a deploy starts with a cold cache.

## 3. The fade

`theCommonsWeb/src/app/globals.css`, `.portal-art::after` inside the
`@media (min-width: 768px)` block.

```css
linear-gradient(
  118deg,
  rgb(var(--color-bg-rgb) / 0)     24%,   /* fade starts */
  ...
  rgb(var(--color-bg-rgb) / 1)     66%    /* fully background */
)
```

- **To move the fade left or right:** shift every stop position by the same amount.
  Keep the spacing between them — that spacing *is* the curve.
- **To make it wider or narrower:** scale the spread around its midpoint.
- **To change the slant:** the angle. Larger = more slanted. Note that stop
  percentages run along the gradient *axis*, whose length depends on viewport aspect
  (`W·sin θ + H·cos θ`), so steeper angles make the fade's on-screen position swing
  more between wide and narrow viewports.

The alpha ramp approximates `alpha = t^2.6` rather than a straight line. A linear ramp
reads as "translucent everywhere"; this one stays under 20% through the first half of
its span, so the painting looks fully opaque well into the fade and then gives way
quickly. Lower the exponent for a more even fade, raise it to hold opacity longer.

### The second gradient

A plain horizontal fade is layered underneath. It is inert in normal cases — the
diagonal has already reached full opacity where it starts — and exists only to seal
the art panel's right edge, which the diagonal alone leaves visible at the top-right
corner on tall, narrow viewports. **If you change the diagonal's angle or end stop,
re-check a tall viewport (e.g. 820×1180) for a hard vertical seam at the panel edge.**

The mobile (`< 768px`) fade is a separate vertical gradient on the same element, with
the same `t^2.6` shape.
