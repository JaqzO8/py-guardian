# Estado de implementación

- **Objetivo:** exigir gratuitamente todas las convenciones del proyecto antes de integrar pushes a `main`.
- **Completado:** 34 pruebas Python, lint y demo local en verde; repositorio privado `JaqzO8/py-guardian` con CI en verde. Terraform desplegó API Gateway, dos Lambdas, SQS, DynamoDB, Secrets Manager y observabilidad en `us-east-1`. El endpoint respondió 200 a un ping firmado y 401 sin firma. Pushes reales 8282568 (success), 893e7dd (failure con hallazgo en línea) y 9165800 (success tras corrección). El PAT fine-grained de `py-guardian/github-token` ya publica estados. La Lambda worker quedó en `LLM_MODE=simulated` (Active/Successful). Push 66a8cda: webhook HTTP 202, estado `success`, comentario `simulado (sin modelo)` y CI en verde.
- **Archivos modificados:** `.gitignore`, `terraform/main.tf`, `README.md`, `PROGRESS.md`.
- **Siguiente paso:** publicar el gate de `guardian-policy.toml` y `.github/workflows/ci.yml`, comprobar CI, hacer público el repositorio tras la auditoría de secretos, proteger `main` con PR y check obligatorio, y demostrar el rechazo de un cambio inválido. Mantenimiento posterior: rotar el PAT de prueba compartido en el chat.
