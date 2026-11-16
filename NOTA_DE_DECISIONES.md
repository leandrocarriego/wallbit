# Nota de decisiones

- **Qué hace la v1:** el cierre del monotributo de punta a punta. El usuario adhiere y vincula ARCA, y cada cobro se clasifica cuando llega: si le falta factura o no se sabe qué es, se le pide en ese momento. El día 1 se calculan todos los cierres, y el contador revisa solo las excepciones (con conversación dentro de la alerta) y aprueba en lote.
- **Garantía regulatoria:** nada le llega al usuario sin una aprobación registrada y un snapshot inmutable. La auditoría es append-only y los datos no salen del sistema.
- **Qué dejé afuera:** ARCA real (AfipSDK detrás del mismo puerto), un modelo de ML local para sugerencias (las respuestas ya quedan como etiquetas), autenticación, Ingresos Brutos y otros regímenes, reapertura de cierres, resolución masiva por contraparte y app nativa.
- **Riesgo más grande:** que el contador siga siendo el cuello de botella si los usuarios no facturan ni responden a tiempo. Lo mitigan los avisos en el momento del cobro, el plan del día, la revisión guiada y el lote.
- **Cómo sabría si funcionó:** clientes por contador (de 30 a cientos), porcentaje de cierres aprobados sin intervención, minutos de revisión por cliente y porcentaje de cobros facturados antes del día 1.
- **IA:** usé Claude Code como par para discutir el diseño, escribir código y tests, y recorrer la demo con Playwright; el alcance, las decisiones de producto y la revisión fueron míos.
