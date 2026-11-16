# Design system — Cierre

- Tokens: [design-system/tokens.json](design-system/tokens.json).
- Implementación web: [web/src/app/globals.css](../web/src/app/globals.css) — variables de shadcn/ui mapeadas a los tokens + utilidades `status-*`, `ink-*`, `surface-*` para Tailwind v4. Dark mode por clase `.dark` (next-themes).
- Fuentes: Geist y Geist Mono vía `next/font` (`--font-geist-sans`, `--font-geist-mono`).

## Reglas rápidas

- `primary` solo para acciones. Los estados usan `status-*`:
  `PENDING_DATA` → pending (ámbar) · `IN_REVIEW` → review (rojo) · `READY` → ready (violeta) · `APPROVED`/`NOTIFIED` → done (verde).
- Texto de estado `text-status-x` sobre `bg-status-x-tint`. El estado siempre lleva texto, nunca solo color.
- Números en `font-mono tabular`, con moneda, alineados a la derecha.
- Bordes antes que sombras; `shadow-pop` solo para menús y toasts.
- Contraste verificado: texto ≥ 4.5:1 en ambos temas, bordes de control y foco ≥ 3:1.

## Componentes → shadcn/ui

| Componente | Base shadcn | Variantes |
|---|---|---|
| Button | `Button` | default, outline, ghost, destructive |
| StatusPill | `Badge` | pending, review, ready, done |
| AlertRow | `Alert` | blocking, waiting, info, resolved |
| KpiCard | `Card` | — |
| CapBar | `Progress` | ok (< 80%), warn (80–99%), over (≥ 100%) |
| DataTable | `Table` + TanStack Table | — |

Si cambia un token: actualizar `tokens.json`, `globals.css`.
