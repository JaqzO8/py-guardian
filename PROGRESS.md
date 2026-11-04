# Estado de implementación

- **Objetivo:** cerrar Py Guardian como demo desplegada con revisión simulada sin proveedor de IA.
- **Completado:** 34 pruebas Python, lint y demo local en verde; repositorio privado `JaqzO8/py-guardian` con CI en verde. Terraform desplegó API Gateway, dos Lambdas, SQS, DynamoDB, Secrets Manager y observabilidad en `us-east-1`. El endpoint respondió 200 a un ping firmado y 401 sin firma. Pushes reales 8282568 (success), 893e7dd (failure con hallazgo en línea) y 9165800 (success tras corrección). El PAT fine-grained de `py-guardian/github-token` ya publica estados: webhook 706259766 activo, push 966a9bc aceptado (HTTP 202), con estado `success` y comentario del worker. La Lambda worker quedó en `LLM_MODE=simulated` (estado Active/Successful); no requiere clave de IA.
- **Archivos modificados:** `.gitignore`, `terraform/main.tf`, `README.md`, `PROGRESS.md`.
- **Siguiente paso:** comprobar que un push real muestre `simulado (sin modelo)` y cerrar el veredicto. Después, sustituir y revocar el PAT compartido en el chat; retirar permisos extra (`Pull requests`, `Workflows`) si no se usan.
