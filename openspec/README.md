# SDD del backend

Preparación del proceso, 2026-11-12. No entrega funcionalidades ni certifica la API existente.
Se adopta la organización de [OpenSpec del frontend](https://github.com/siramUNTDF/siram-front/tree/main/openspec):
`schema: spec-driven`, capacidades, proposal, design, tasks y cambios archivados por fecha.
No se instalaron herramientas ni se ejecutaron generadores. La edición manual es suficiente.

## Fuentes y estructura

Leer [AGENTS.md](../AGENTS.md), el [README](../README.md), las specs de las capacidades afectadas
y las decisiones de siram-proyecto antes de cambiar comportamiento. El modelo v2 sigue declarado
borrador; no tratar sus requisitos como implementación ya existente. El frontend aporta ejemplos
de experiencia y metodología, no una especificación retrospectiva del backend.

```text
openspec/
  config.yaml
  README.md
  specs/<capacidad>/spec.md
  changes/<nombre-del-cambio>/
    .openspec.yaml
    proposal.md
    design.md                 # cuando hay decisiones técnicas relevantes
    tasks.md
    specs/<capacidad>/spec.md  # deltas de comportamiento
  changes/archive/AAAA-MM-DD-<nombre-del-cambio>/
```

`specs/` empieza sin capacidades: no significa que la API esté ausente, sino que todavía no se
ha establecido una línea base en OpenSpec. Al abordar una capacidad existente, documentar su
comportamiento actual con evidencia de código/pruebas y separar las brechas de dominio.
Las specs vigentes describen comportamiento establecido; no garantizan ejecución verificada.
Cada entrega debe indicar qué escenarios se ejecutaron realmente.

## Flujo proporcional

1. **Contexto:** leer fuentes vigentes, código, contratos, migraciones y pruebas de la capacidad.
   Identificar comportamiento actual, requisito pendiente y contradicciones, con rutas.
2. **Propuesta:** crear `changes/<nombre-en-kebab-case>/proposal.md`: problema, alcance, resultado
   esperado, exclusiones, capacidades e impacto. Usar encabezados `Why`, `What Changes`,
   `Capabilities` (`New Capabilities` / `Modified Capabilities`) e `Impact`, como en el front.
   Agregar `.openspec.yaml` con `schema: spec-driven` y `created: AAAA-MM-DD` (fecha real).
3. **Aceptación:** escribir escenarios observables en los deltas, con datos ficticios. Incluir
   éxito, validaciones, errores y permisos pertinentes. No confundir lo propuesto con lo vigente.
4. **Diseño:** agregar `design.md` si cambia contrato, modelo/migraciones, permisos, transacciones,
   concurrencia, seguridad o hay alternativas relevantes. Registrar contexto, decisiones, impacto
   en consumidores/datos, riesgos y transición. Omitirlo con motivo en proposal si no aporta.
5. **Tareas:** descomponer en pasos pequeños y dependencias en `tasks.md`, con checks de
   implementación y verificación separados. Una tarea bloqueada queda abierta con causa.
6. **Implementación y pruebas:** trabajar dentro del alcance autorizado. Anotar comando, entorno,
   resultado y limitaciones; marcar `[x]` solo lo completado con evidencia. No pedir aprobación
   para cada artefacto; aclarar únicamente dudas que cambien el alcance o decisiones de dominio.
7. **Sincronización:** al entregar comportamiento, incorporar ADDED/MODIFIED/REMOVED/RENAMED en
   `specs/<capacidad>/spec.md`. La spec vigente usa `Requirements`, sin encabezados de delta.
   Mantener los escenarios y trazabilidad; no copiar requisitos pendientes como entregados.
8. **Cierre:** revisar aceptación, pruebas, contrato y documentación. Solo con trabajo completo,
   mover el cambio a `changes/archive/AAAA-MM-DD-<nombre>/`, conservando todos sus artefactos.
   No archivar con tareas o verificaciones obligatorias pendientes; separar trabajo futuro en
   otro cambio explícito, sin marcarlo realizado. No sobrescribir un archivo existente.
9. **Continuidad:** registrar resultado, verificaciones, límites y referencias reales a commits/PR
   en `MEMORY.md` de siram-proyecto. Si falta ese repo, informar el registro pendiente.

Una corrección menor de documentación o pruebas **sin cambio funcional** puede usar solo el
diff y una descripción de PR/registro breve: problema, archivos, verificación y límites. No exige
proposal/design/specs ni un archivo vacío por paso. Actualizar memoria al cerrar un cambio
significativo. Esta preparación usa ese registro simplificado en la memoria compartida.

## Plantilla breve para cambios funcionales

En `proposal.md`, además de los encabezados anteriores:

```markdown
## Why
Problema y evidencia del comportamiento actual (rutas/pruebas).
## What Changes
Comportamiento esperado, aceptación y fuera de alcance.
## Capabilities
### New Capabilities
- <capacidad>: ...
### Modified Capabilities
- <capacidad>: ...
## Impact
API, consumidores, datos/migraciones, permisos, documentos y dependencias.
Diseño: archivo design.md, o motivo por el que se omite.
```

En el delta `specs/<capacidad>/spec.md` (ejemplo de formato, no requisito implementado):

```markdown
## ADDED Requirements
### Requirement: <comportamiento observable>
El sistema SHALL <resultado y condiciones>.
#### Scenario: <situación>
- **GIVEN** <estado inicial>
- **WHEN** <acción>
- **THEN** <resultado comprobable>
```

Para `MODIFIED Requirements`, incluir el requisito completo actualizado y sus escenarios.
Para eliminar o renombrar, usar `REMOVED Requirements` o `RENAMED Requirements` y justificar
compatibilidad y transición; no eliminar requisitos de dominio para encajar con el código.

En `tasks.md`:

```markdown
## 1. Implementación
- [ ] 1.1 <paso concreto, módulos y dependencia>
## 2. Verificación y cierre
- [ ] 2.1 <escenarios, comando y resultado esperado>
- [ ] 2.2 Revisar API/datos, sincronizar specs y documentación
- [ ] 2.3 Revisar diff y registrar cierre en memoria
```

## Validación y siguiente entrega

No hay validador documental configurado ni CLI OpenSpec disponible en el entorno de preparación.
Si ya existe CLI en el entorno de trabajo futuro, usar `openspec validate --help` para confirmar
la sintaxis local y validar el cambio; no instalarlo solo para editar Markdown. En caso contrario,
revisar manualmente estructura, escenarios, enlaces y estado de tareas; ejecutar `git diff --check`.
No declarar validación OpenSpec a partir de esa revisión manual.

La siguiente entrega de **pruebas, CI y documentación** debe inventariar pruebas y automatización
existentes, proponer el alcance y separar pruebas del comportamiento actual de requisitos nuevos.
Usar bases y adjuntos aislados; registrar resultados reales y fallos previos. Incorporar CI solo
si está autorizado, con checks reproducibles y sin secretos/datos compartidos. No inventar un
baseline verde ni generar pruebas cuyo único objetivo sea encontrar estos Markdown.
