# Git Flow

## Ramas

| Rama | Propósito | Sale de | Mergea a | Protegida |
|---|---|---|---|---|
| `main` | Lo que está en producción. Cada merge = un tag semver | — | — | Sí |
| `dev` | Integración; siempre verde y desplegable a staging | `main` | — | Sí |
| `feature/<id>-<slug>` | Una funcionalidad o cambio | `dev` | `dev` | No |
| `fix/<id>-<slug>` | Bug no urgente | `dev` | `dev` | No |
| `release/<x.y.0>` | Estabilización previa a salida (solo fixes, docs, versión) | `dev` | `main` **y** `dev` | Sí |
| `hotfix/<x.y.z>` | Bug urgente en producción | `main` | `main` **y** `dev` | No |

Ejemplos: `feature/WB-12-batch-approval`, `fix/WB-40-fx-rounding`, `release/0.3.0`, `hotfix/0.3.1`.

## Flujo

1. `git switch dev && git pull && git switch -c feature/WB-12-batch-approval`
2. Commits chicos con Conventional Commits.
3. `git rebase dev` antes de abrir el PR (historia lineal en features).
4. PR → `dev`. **Squash merge**. Se borra la rama.
5. Release: `release/x.y.0` desde `dev`, se bumpea versión y CHANGELOG, PR → `main` (**merge commit**), tag `vX.Y.0`, back-merge a `dev`.
6. Hotfix: igual que release pero desde `main`, bump de patch.

## Commits — Conventional Commits

```
<type>(<scope>): <descripción en imperativo, minúscula, sin punto>

[cuerpo opcional: el porqué]

[footer: Refs WB-12 | BREAKING CHANGE: ...]
```

- **types**: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `ci`, `build`, `style`, `revert`
- **scopes**: `api`, `worker`, `web`, `mobile`, `tax-engine`, `classification`, `closing`, `infra`, `ci`, `docs`
- Ej: `feat(tax-engine): add 12-month rolling cap check`
- Validado por `commitlint` en el hook `commit-msg`.

## Pull Requests

- Título = mensaje de commit convencional (es el que queda al squashear).
- Template: **Qué** / **Por qué** / **Cómo probarlo** / **Riesgos** / checklist (tests, migración, docs, impacto en cálculo fiscal).
- Requisitos para merge:
  - CI verde (lint, types, unit, integration, e2e, build).
  - Cobertura del `tax_engine` ≥ 95% y sin bajar la global.
  - 1 aprobación (en el proyecto real: el contador revisa todo PR con label `tax-logic`).
  - Sin conflictos; rama actualizada con la base.
- PRs chicos (< 400 líneas cambiadas como guía).

## Versionado

- **SemVer**. `0.x` mientras sea prototipo/beta.
- `CHANGELOG.md` generado desde los commits.
- Cambios en parámetros fiscales **no** son releases de código: se versionan en la DB (`tax_parameters`).
