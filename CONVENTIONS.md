# Convenciones del Proyecto

Esta es la especificación para el equipo. Su configuración ejecutable está en
`guardian-policy.toml`; el job `guardian-policy` de `.github/workflows/ci.yml`
falla ante cualquier regla activada. Las comprobaciones se aplican a las líneas
añadidas del push o PR; los requisitos de tests se evalúan por cambio completo.

## Nomenclatura
- Python: funciones y variables en `snake_case`, clases en `PascalCase`, constantes en `UPPER_SNAKE`.
- Archivos Python en `snake_case.py`.
- Los nombres deben describir lo que hacen: prohibido `data`, `tmp`, `x`, `foo` para valores con significado de negocio.

## Arquitectura
- Capas: `api/` (HTTP) → `services/` (lógica de negocio) → `repositories/` (acceso a datos).
- `api/` nunca importa de `repositories/` directamente.
- Los servicios no deben conocer detalles de HTTP (`request`, `response`).

## Manejo de errores
- Prohibido `except:` desnudo o `except Exception: pass`.
- En `services/`, las excepciones lanzadas usan tipos propios importados de `errors.py`.

## Calidad
- Prohibido `print()` en código de producción; usa `logging`.
- Toda función pública nueva lleva type hints y docstring de una línea.
- Todo cambio en código Python de producción incluye un cambio en `tests/`.
- Los TODO llevan ticket: `TODO(PROJ-123)`.

## Seguridad
- Ningún secreto en el repositorio; se leen de variables de entorno o del gestor de secretos.

## Commits
- Conventional Commits: `feat|fix|docs|refactor|test|chore(ámbito): descripción`.
